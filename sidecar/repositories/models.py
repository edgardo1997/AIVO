"""ORM mappings used by the async profile API.

Schema creation and migrations belong exclusively to ``DatabaseManager``.
These classes map existing tables; they must never create or alter them.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, default="local-user")
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="Local User")
    avatar: Mapped[str] = mapped_column(String, default="")
    theme: Mapped[str] = mapped_column(String, default="light")
    timezone: Mapped[str] = mapped_column(String, default="")
    locale: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[str] = mapped_column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )


class UserPreferenceV2(Base):
    __tablename__ = "user_preferences_v2"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )


class OAuthTransactionModel(Base):
    __tablename__ = "oauth_transactions"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    state_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nonce_hash: Mapped[str] = mapped_column(String, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String, nullable=False)
    code_verifier_hash: Mapped[str] = mapped_column(String, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="created")
    used_at: Mapped[str] = mapped_column(String, nullable=True)
    owner_session_id: Mapped[str] = mapped_column(String, default="")
    owner_user_id: Mapped[str] = mapped_column(String, default="")
    correlation_id: Mapped[str] = mapped_column(String, default="")
