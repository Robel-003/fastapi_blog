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

from routers import posts, users




# creating our db tables (looking at models inheriting from base, and creates tables if they don't already exist)
 # lifespan func, modern way that handles startup/shutdown events (in fastapi)
    # startup (engine.begin() creates an async connection)
    # <-- establishing async db connection to start transaction
        # run_sync() <- providing synchronous style connection interface to funct passed into it
        # Base.metadata.create_all <- using that interface to create db tables
        # await <- allowing asynch connection to complete before proceeding
        # yield <- everything before yield happens during app startup (everything after happens during app shutdown )
@asynccontextmanager
async def lifespan(_app: FastAPI): 
    # startup
    async with engine.begin() as conn:
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



# including posts/users routers
# tags param organizes /docs page to create collapsable sections for specific routes
app.include_router(users.router, prefix="/api/users", tags=["users"]) 
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])



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


# exception error handling
@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(
    request: Request, exception: StarletteHTTPException
):
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
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
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
