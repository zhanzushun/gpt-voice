from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import requests
from datetime import datetime, timedelta
import jwt
import random
import string
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import RpcRequest
import logging
import os

import config

router = APIRouter()

aliyun_client = AcsClient(config.ALIYUN_APP_ID, config.ALIYUN_APP_KEY, 'cn-hangzhou')

verification_codes = {}

def generate_verification_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_sms(phone_number, code):
    request = RpcRequest('Dysmsapi', '2017-05-25', 'SendSms')
    request.set_accept_format('json')
    request.set_method('POST')
    request.set_protocol_type('https')  # https | http
    request.set_version('2017-05-25')
    request.set_action_name('SendSms')
    request.add_query_param('RegionId', "cn-hangzhou")
    request.add_query_param('PhoneNumbers', phone_number)
    request.add_query_param('SignName', config.ALIYUN_SMS_SIGN_NAME)
    request.add_query_param('TemplateCode', config.ALIYUN_SMS_TEMPLATE_CODE)
    request.add_query_param('TemplateParam', f'{{"code":"{code}"}}')
    response = aliyun_client.do_action_with_exception(request)
    return response

class PhoneNumber(BaseModel):
    phone: str

@router.post("/api_12/send_code")
async def send_code(data: PhoneNumber):
    phone = data.phone
    code = generate_verification_code()
    verification_codes[phone] = code
    try:
        logging.info(f'send_sms({phone}, {code})')
        send_sms(phone, code)
    except Exception as e:
        logging.exception('发送短信验证码失败')
        raise HTTPException(status_code=500, detail=f"发送短信验证码失败: {e}")
    return {"message": "Verification code sent successfully"}


ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


class LoginRequest(BaseModel):
    phone: str
    code: str
    
@router.post("/api_12/login")
async def login(data: LoginRequest):
    phone = data.phone
    code = data.code
    if verification_codes.get(phone) == code:
        access_token = create_access_token(data={"sub": phone}, expires_delta=timedelta(days=7))
        logging.info(f'login,user={phone}')
        return {"token": access_token}
    else:
        logging.error(f'验证码无效, 手机号码为:{phone}')
        raise HTTPException(status_code=400, detail="验证码无效")


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        phone = payload.get("sub")
        if phone is None:
            logging.error(f'验证码无效, 手机号码为:{phone}')
            raise HTTPException(status_code=401, detail="Invalid token")
        return phone
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    

class ErrorRequest(BaseModel):
    error: str

def create_flutter_error_logger():
    log_directory = "logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    log_file = os.path.join(log_directory, "flutter_errors.log")
    logger = logging.getLogger('flutter_error_logger')
    logger.setLevel(logging.ERROR)
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger

flutter_error_logger = create_flutter_error_logger()

# 在其他需要保护的路由中使用 verify_token 依赖
@router.post("/api_12/error")
async def post_error(request: ErrorRequest = Body(...), phone: str = Depends(verify_token)):
    flutter_error_logger.error(f'flutter client got error, phone={phone}')
    flutter_error_logger.error(request.error)
    return {'result': 'ok'}
