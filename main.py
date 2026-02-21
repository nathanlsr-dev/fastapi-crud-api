import json
import os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel
from typing import Annotated
from passlib.context import CryptContext
from jose import JWTError, jwt

# Configurações de segurança
SECRET_KEY = "arcl4ajKv61T8XA21TC1ryC4CkZdTuf9ZEaJV4cpd9khVzSPuH"  # Gere uma real forte (ex: use um gerador online ou openssl)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

fake_users_db = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("40028922"),  # Mude a senha aqui pra algo que você lembre
    }
}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db, username: str):
    if username in db:
        return db[username]

def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=username)
    if user is None:
        raise credentials_exception
    return user

DB_FILE = "items.json"  # Mude pra "D:/NLSR/meu-primeiro-api/items.json" se der permissão ainda

# Carrega DB se existir, senão inicia vazia
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        items_db = json.load(f)
    # Calcula próximo ID baseado no maior existente
    next_id = max(item["id"] for item in items_db) + 1 if items_db else 1
else:
    items_db = []
    next_id = 1

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

class ItemOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    price: float
    tax: float | None = None
    price_with_tax: float | None = None    

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],              # Em produção, mude pra domínios reais, ex: ["https://seu-frontend.com"]
    allow_credentials=True,
    allow_methods=["*"],              # Permite GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],              # Permite headers como Authorization, Content-Type
)

@app.post("/items/", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    item: Item,
    current_user: Annotated[dict, Depends(get_current_user)]
    ):

    global next_id
    item_dict = item.model_dump()
    if item.tax is not None:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})

    item_dict["id"] = next_id
    items_db.append(item_dict)

    # Salva no arquivo JSON
    with open(DB_FILE, "w") as f:
        json.dump(items_db, f, indent=2)

    next_id += 1
    return item_dict

@app.get("/")
async def root():
    return {"message": "API Mini E-commerce rodando! Acesse /docs para Swagger"}

@app.get("/items/{item_id}")
async def read_item(item_id: int):  # Mudei nome pra read_item (boa prática)
    for item in items_db:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item não encontrado")

@app.get("/items/")
async def read_items():
    return items_db

@app.put("/items/{item_id}")
async def update_item(
    item_id: int, item_update: Item,
    current_user: Annotated[dict, Depends(get_current_user)]
    ):
    for i, existing_item in enumerate(items_db):
        if existing_item["id"] == item_id:
            # Atualiza só os campos que vieram no body
            updated_item = {**existing_item, **item_update.model_dump(exclude_unset=True)}
            
            # Recalcula tax se mudou
            if "tax" in item_update.model_dump() or "price" in item_update.model_dump():
                if updated_item.get("tax") is not None:
                    updated_item["price_with_tax"] = updated_item["price"] + updated_item["tax"]
                else:
                    updated_item.pop("price_with_tax", None)
            
            items_db[i] = updated_item
            
            # Salva no arquivo JSON DEPOIS da atualização
            with open(DB_FILE, "w") as f:
                json.dump(items_db, f, indent=2)
            
            return updated_item  # Return fora do with
        
    raise HTTPException(status_code=404, detail="Item não encontrado")

@app.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    current_user: Annotated[dict, Depends(get_current_user)]
    ):
    for i, item in enumerate(items_db):
        if item["id"] == item_id:
            deleted = items_db.pop(i)
            
            # Salva no arquivo JSON DEPOIS de deletar
            with open(DB_FILE, "w") as f:
                json.dump(items_db, f, indent=2)
            
            return {"message": f"Item {item_id} deletado com sucesso"}                
        
    raise HTTPException(status_code=404, detail="Item não encontrado")

@app.post("/login")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}    