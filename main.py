import os
import sys
import traceback


def _startup_crash_log_path() -> str:
    return os.path.join(os.getcwd(), "startup_crash.log")


def _write_startup_crash(exc: BaseException) -> None:
    try:
        with open(_startup_crash_log_path(), "w", encoding="utf-8") as handle:
            handle.write("ColorAnalyzer startup crash\n\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=handle)
    except Exception:
        pass


def _install_global_excepthook() -> None:
    def _hook(exc_type, exc_value, exc_traceback):
        try:
            with open(_startup_crash_log_path(), "w", encoding="utf-8") as handle:
                handle.write("ColorAnalyzer unhandled exception\n\n")
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=handle)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook


try:
    _install_global_excepthook()
    from mobile_app import ColorAnalyzerMobileApp
except Exception as exc:
    _write_startup_crash(exc)
    raise


if __name__ == "__main__":
    ColorAnalyzerMobileApp().run()
