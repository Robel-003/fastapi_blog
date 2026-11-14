from datetime import datetime

# basemodel is base class pydantic models inherit from
# configdict is modern pydantic v.2 way to configure models
# field lets us add constraints(min,max len)
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# user schemas
class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    # EmailStr from pydantics validates email string (no need for use to validate)
    email: EmailStr = Field(max_length=120)


class UserCreate(UserBase):
    pass


# UserResponse class is inheriting from UserBase which contains user email, which will be shown in public API (privacy concern),
# will change later separating public/private schemas
class UserResponse(UserBase):
    model_config = ConfigDict(
        from_attributes=True
    )  # set to true b/c want pydantic to read from sql model

    id: int
    image_file: str | None
    image_path: str  # image_path is a property from our user model (reference from model.py file)


# schema for updating user
class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    image_file: str | None = Field(default=None, min_length=1, max_length=200)


# base schema, what's shared between what is creating/returning post
class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)


# schema for updating a post (title/content)
class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1)


# inherits from PostBase class
class PostCreate(PostBase):
    user_id: int  # temporary for testing. After adding authentication, we'll get current user from session


# what's returned from api
class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    # when sqlalchemy loads post, it'll also load related user
    # pydantic sees author field, validates user object against UserResponse, then includes user date in API response
    author: UserResponse
