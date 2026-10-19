"""Strava athletes and their encrypted OAuth tokens."""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from trainsync.core.orm import Base, utc_timestamp


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = utc_timestamp(default_now=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    athlete_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = utc_timestamp()
    scope: Mapped[str] = mapped_column(Text)
