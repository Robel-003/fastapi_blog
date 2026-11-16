from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from database import get_db
from schemas import PostResponse, UserCreate, UserResponse, UserUpdate


router = APIRouter()  # <- what we'll decorate routes with instead of our app


# creating new user
@router.post(
    "",  # actual path is in main.py file, empty here b/c of prefix in main file
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,  # proper http response for creating user
)
# 2nd param is our dependency injection,
# before running "db:" function, call get_db function from database.py file, and pass result as db param
# get_db func creates a session and yields it. Each request to get_db gets its own db session
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    # check if username already exist
    result = await db.execute(
        select(models.User).where(models.User.username == user.username),
    )
    # getting first user object or none of no match
    existing_user = result.scalars().first()
    # raise exception is user already exists in db
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    # check if email already exist
    result = await db.execute(
        select(models.User).where(models.User.email == user.email),
    )
    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    # new user created if user/email don't already exist
    new_user = models.User(username=user.username, email=user.email)
    # adding and committing new user to db, 3 step process
    # 1.new user is staged to be added, 2.new user is committed to db, 3.refresh reloads new user to db
    db.add(new_user)
    # actual db operations happen at commit/refresh (await needed in this case), not in db.add()
    await db.commit()
    await db.refresh(new_user)
    return new_user


# getting specific user by path parameter
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # matching user by their user_id
    result = await db.execute(
        select(models.User).where(models.User.id == user_id),
    )
    user = result.scalars().first()
    # return user if user already exist, if not raise proper exception
    if user:
        return user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


# api route for getting user post (response model is list of post responses)
@router.get("/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    # first verify if user exists, then query for their post
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
    )
    posts = result.scalars().all()
    return posts


# API endpoint for patching(updating) user
@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    # first find user if they exist
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # check if newly requested username/email is diff from curr username/email, and if it doesn't already exist within db
    if user_update.username is not None and user_update.username != user.username:
        result = db.execute(
            select(models.User).where(models.User.username == user_update.username),
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

    if user_update.email is not None and user_update.email != user.email:
        result = db.execute(
            select(models.User).where(models.User.email == user_update.email),
        )
        existing_email = result.scalars().first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # once all the updated data is safe to udpate, update only those provided fields
    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.image_file is not None:
        user.image_file = user_update.image_file

    await db.commit()
    await db.refresh(user)
    return user


# api route for deleting user(and user's data)
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    # raise error if user does not exist
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # delete operation interacts with session that requires await/async mode
    await db.delete(user)
    await db.commit()
