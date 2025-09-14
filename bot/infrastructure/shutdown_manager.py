import asyncio
import logging
import signal
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class ShutdownManager:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self._tasks: Set[asyncio.Task] = set()
        self._shutdown_callbacks: List[callable] = []

    async def setup_signal_handlers(self):
        """Set up asyncio signal handlers for graceful shutdown"""
        loop = asyncio.get_running_loop()

        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, lambda s=sig: self._handle_signal(s))

        if hasattr(signal, "SIGHUP"):
            loop.add_signal_handler(
                signal.SIGHUP, lambda: self._handle_signal(signal.SIGHUP)
            )

    def _handle_signal(self, signum: int) -> None:
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_event.set()

    def register_task(self, task: asyncio.Task) -> None:
        """Register a task for cleanup during shutdown"""
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def add_shutdown_callback(self, callback: callable) -> None:
        """Add a callback to run during shutdown"""
        self._shutdown_callbacks.append(callback)

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal"""
        await self.shutdown_event.wait()

    async def cancel_tasks(self) -> None:
        """Cancel all registered tasks"""
        if not self._tasks:
            return

        logger.info(f"Cancelling {len(self._tasks)} tasks...")

        for task in self._tasks.copy():
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def run_shutdown_callbacks(self) -> None:
        """Run all shutdown callbacks"""
        for callback in self._shutdown_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error running shutdown callback: {e}")

    async def shutdown(self) -> None:
        """Perform complete shutdown sequence"""
        logger.info("Starting graceful shutdown...")
        await self.cancel_tasks()
        await self.run_shutdown_callbacks()
        logger.info("Shutdown complete")

    @property
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        return self.shutdown_event.is_set()

    async def wait_with_shutdown(self, coro_or_future, timeout: Optional[float] = None):
        """Wait for a coroutine/future or shutdown, whichever comes first"""
        shutdown_task = asyncio.create_task(self.shutdown_event.wait())

        if asyncio.iscoroutine(coro_or_future):
            main_task = asyncio.create_task(coro_or_future)
        elif asyncio.isfuture(coro_or_future) or hasattr(coro_or_future, "__await__"):
            main_task = coro_or_future
        else:
            raise TypeError(f"Expected coroutine or future, got {type(coro_or_future)}")

        try:
            done, pending = await asyncio.wait(
                [main_task, shutdown_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if shutdown_task in done:
                if not main_task.done():
                    main_task.cancel()
                raise asyncio.CancelledError("Shutdown requested")

            if main_task in done:
                return await main_task

            raise asyncio.TimeoutError()

        except Exception:
            for task in [main_task, shutdown_task]:
                if not task.done():
                    task.cancel()
            raise
