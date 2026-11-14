from typing import Annotated

# Depends is dependency injection (how we'll inject db session into our routes)
from fastapi import Depends, FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Jinja2 templates serves up HTML pages to users while maintaining JSON endpoints for backend API
# jinja2 templates require the request object
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException  #

from sqlalchemy import select
from sqlalchemy.orm import (
    Session,
)  # Session import is for type hints (IDE knows what type our db param is)

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

# creating our db tables
# looking at all our models inheriting from base, and creates tables if they don't already exist
Base.metadata.create_all(
    bind=engine
)  # safe to run multiple times, if tables exist, nothing happens


# app object used to define all our routes
app = FastAPI()

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
def home(
    request: Request, db: Annotated[Session, Depends(get_db)]
):  # jinja2 requires request param to work
    result = db.execute(select(models.Post))  # querying db for all posts
    posts = result.scalars().all()
    # 3rd param passing in dictionary
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "Home"},
    )  # returning all posts to template response


# api route for a single post
@app.get("/posts/{post_id}", include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
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
def user_posts_page(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
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
    status_code=status.HTTP_201_CREATED,  # proper response for creating user
)
# 2nd param is our dependency injection,
# before running "db:" function, call get_db function from database.py file, and pass result as db param
# get_db func creates a session and yields it. Each request to get_db gets its own db session
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    # check if username already exist
    result = db.execute(
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
    result = db.execute(
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
    db.commit()
    db.refresh(new_user)
    return new_user


# getting specific user by path parameter
@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    # matching user by their user_id
    result = db.execute(
        select(models.User).where(models.User.id == user_id),
    )
    user = result.scalars().first()
    # return user if user already exist, if not raise proper exception
    if user:
        return user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


# api route for getting user post
# response model is a list of post responses
@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
    # first verify if user exists, then query for their post
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return posts


# API endpoint for patching(updating) user
@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(select(models.User).where(models.User.id == user_id))
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

    db.commit()
    db.refresh(user)
    return user


# api route for deleting user(and user's data)
@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    # raise error if user does not exist
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.delete(user)
    db.commit()


# API endpoint for getting all our posts
@app.get("/api/posts", response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post))
    posts = result.scalars().all()
    return posts


# api route for creating new post
@app.post(
    "/api/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == post.user_id))
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
    db.commit()
    db.refresh(new_post)
    return new_post


# api route for getting post
@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


# api route for updating full post
# post_data will contain data from request body when attempting to update post
@app.put("/api/posts/{post_id}", response_model=PostResponse)
def update_post_full(
    post_id: int, post_data: PostCreate, db: Annotated[Session, Depends(get_db)]
):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    # first check if post exist before updating
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    # check if user who's updating post actually exist
    if post_data.user_id != post.user_id:
        result = db.execute(
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

    db.commit()
    db.refresh(post)
    return post


# api route for updating partial post (patching post)
@app.patch("/api/posts/{post_id}", response_model=PostResponse)
def update_post_partial(
    post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]
):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
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

    db.commit()
    db.refresh(post)
    return post


# api route for deleting post
# for delete, a 204 no content response is returned (request succeded but no response body)
@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    # first raise an error if post doesn't exist, then delete post
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    db.delete(post)
    db.commit()
    # TODO: add ownership checks so only author of post can delete a post


# exception error handling
@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    # setting up a message if exception has detail, otherwise let user know error occurred
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    # if issue is with api route, raise exception with proper error/message
    # if not api route issue, return a template response
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
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
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )
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
