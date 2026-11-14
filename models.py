from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# our user model ("users" as table name), #id as primary key (auto increments)
# username/email are unique (no two names/emails are the same)
# image_file str or none (pic or file name added)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    image_file: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None,
    )

    # 1-to-many relationship (one user has many posts)
        # back_populates="author" lets us dig into user's posts thru "user.posts"
        # cascade="all, delete-orphan" <-- this delete's a user and all its posts
    posts: Mapped[list[Post]] = relationship(back_populates="author", cascade="all, delete-orphan")

    # if user has img, return img thru below file path or return a defualt img thru below file path
    @property
    def image_path(self) -> str:
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        return "/static/profile_pics/default.jpg"


# our post table
# user_id links post to users foreign_key (ForeignKey("users.id")) <-- this must reference a valid user
# user_id index set to true to easily query user by user_id
# primary keys automatically get index but foreign keys don't
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    date_posted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # many-to-1, many posts associated with one author
    # back_populate to find author by a post
    author: Mapped[User] = relationship(back_populates="posts")
