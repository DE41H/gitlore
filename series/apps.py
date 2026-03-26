from django.apps import AppConfig


class SeriesConfig(AppConfig):
    name = "series"

    def ready(self) -> None:
        import series.signals  # noqa: F401

        return super().ready()
