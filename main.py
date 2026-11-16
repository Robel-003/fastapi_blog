from typing import Annotated

from contextlib import asynccontextmanager

# fastapi's default exception hanlders for async hanlders
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)

# Depends is dependency injection (how we'll inject db session into our routes)
from fastapi import Depends, FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

# Jinja2 templates serves up HTML pages to users while maintaining JSON endpoints for backend API
# jinja2 templates require the request object
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException  #

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# import selectinload for eager loading relationships (important for async)
from sqlalchemy.orm import selectinload

import models  # getting access to our post/user models

# Base/engine are for creating tables, get_db is db function that provides sessions
from database import Base, engine, get_db
from schemas import (
    PostCreate,
    PostResponse,
    UserCreate,
    UserResponse,
    PostUpdate,
    UserUpdate,
)


# creating our db tables (looking at models inheriting from base, and creates tables if they don't already exist)
@asynccontextmanager
async def lifespan(
    _app: FastAPI,
):  # lifespan func, modern way that handles startup/shutdown events (in fastapi)
    # startup (engine.begin() creates an async connection)
    async with (
        engine.begin() as conn
    ):  # <-- establishing async db connection to start transaction
        # run_sync() <- providing synchronous style connection interface to funct passed into it
        # Base.metadata.create_all <- using that interface to create db tables
        # await <- allowing asynch connection to complete before proceeding
        # yield <- everything before yield happens during app startup (everything after happens during app shutdown )
        await conn.run_sync(Base.metadata.create_all)
    yield
    # shutdown (disposing of async sqlalchemy engine)
    await engine.dispose()


# app object used to define all our routes
app = FastAPI(lifespan=lifespan)  # registering lifespan function with FastAPI

# mount method takes 3 arguments
# 1.url path where static files are accessible
# 2.instance that points to static directory
# 3.name we can use to reference in our templates
# any file in our static directory is accessible thru /static in browser
app.mount("/static", StaticFiles(directory="static"), name="static")

# media directory for user uploaded content
app.mount("/media", StaticFiles(directory="media"), name="media")


# creating templates object that looks in templates directory for templates files
templates = Jinja2Templates(directory="templates")


# home route responding to get req at root url
# stacking decoraters to show home page and post page (stacking decoraters FastAPI feature)
# include_in_schema hides this routes from /docs api
@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
async def home(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
):  # selectinload, instance of eager loading (executing additional query to retrieve related objects)
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author)),
    )  # querying db for all posts
    posts = result.scalars().all()
    # 3rd param passing in dictionary
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "Home"},
    )  # returning all posts to template response


# api route for a single post
@app.get("/posts/{post_id}", include_in_schema=False)
async def post_page(
    request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post:
        title = post.title[:50]  # title contains first 50 characters
        # returning html template
        return templates.TemplateResponse(
            request,
            "post.html",
            {"post": post, "title": title},
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


# html template route for viewing user posts
@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
# func can be referenced using url_for() in our templates
async def user_posts_page(
    request: Request,
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # selectinload not needed in first query b/c we're not accessing any relationships on the user
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    # selectinload needed in 2nd query b/c our template accesses a many-to-1 relationship (Post.author)
    # making a call to db where a query will be made to related objects
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


# creating a new user
@app.post(
    "/api/users",
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
@app.get("/api/users/{user_id}", response_model=UserResponse)
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
@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
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
@app.patch("/api/users/{user_id}", response_model=UserResponse)
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
@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
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


# API endpoint for getting all our posts
@app.get("/api/posts", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author))
    )
    posts = result.scalars().all()
    return posts


# api route for creating new post
@app.post(
    "/api/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(post: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=post.user_id,
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)
    return new_post


# api route for getting post
@app.get("/api/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


# api route for updating full post
# post_data will contain data from request body when attempting to update post
@app.put("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int, post_data: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    # first check if post exist before updating
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    # check if user who's updating post actually exist
    if post_data.user_id != post.user_id:
        result = await db.execute(
            select(models.User).where(models.User.id == post_data.user_id)
        )
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    # updating user content and commit to db
    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    await db.commit()
    # telling refresh to load specific relationships using attribute name (refresh post and load author relationship)
    await db.refresh(post, attribute_names=["author"]) 
    return post


# api route for updating partial post (patching post)
@app.patch("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    # first check if post exist before updating
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    # only udpate fields client actually sent
    # exclude_unset=true only updates what user changed (model_dump() provides a dict)
    update_data = post_data.model_dump(exclude_unset=True)
    # loop over model_dump() dict updating what's being changed
    # field is the title attribute to be changed, and value is the new title
    # we then set attribute(setattr) for the post we're updating,
    # and update the title(field) with the new title(value)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


# api route for deleting post
# for delete, a 204 no content response is returned (request succeded but no response body)
@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    # first raise an error if post doesn't exist, then delete post
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    await db.delete(post)
    await db.commit()
    # TODO: add ownership checks so only author of post can delete a post


# exception error handling
@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    # using fastapi async default handlers (was using json response before)
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    # setting up a message if exception has detail, otherwise let user know error occurred
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


# validation error handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )



## 200 OK - Successful GET, PUT, or PATCH
## 201 Created - Successful POST for users and posts
## 204 No Content - Successful DELETE
## 400 Bad Request - Duplicate username/email when creating user
## 404 Not Found - Resource doesn't exist (user or post)
## 422 Unprocessable Entitv - Validation error (automatic from Pdantic)*
