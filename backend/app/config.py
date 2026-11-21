import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    home: Path
    database_url: str
    origin: str = "http://127.0.0.1:5173"
    quality_threshold: float = 0.15
    spark_master: str = "local[1]"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        home = Path(os.getenv("CLOUDLAKE_HOME", ".runtime")).resolve()
        threshold = float(os.getenv("CLOUDLAKE_QUALITY_THRESHOLD", "0.15"))
        if not 0 <= threshold <= 1:
            raise ValueError("CLOUDLAKE_QUALITY_THRESHOLD must be between 0 and 1")
        return cls(
            home=home,
            database_url=os.getenv("CLOUDLAKE_DATABASE_URL", "sqlite:///" + (home / "metadata.db").as_posix()),
            origin=os.getenv("CLOUDLAKE_ORIGIN", "http://127.0.0.1:5173"),
            quality_threshold=threshold,
            spark_master=os.getenv("CLOUDLAKE_SPARK_MASTER", "local[1]"),
        )
