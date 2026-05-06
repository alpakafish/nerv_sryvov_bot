from cryptography.fernet import Fernet
import os

def get_encryption_key():
    """
    Получает ключ шифрования из переменной окружения.
    Если ключа нет - генерирует новый (только для локальной разработки)
    """
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # Для локальной разработки генерируем ключ
        # На Render'e ключ должен быть задан в переменных окружения
        key = Fernet.generate_key().decode()
        print(f"⚠️ ВНИМАНИЕ: Создан новый ключ шифрования для локальной разработки")
        print(f"Сохрани этот ключ для Render: {key}")
    return key.encode()

def encrypt_message(message: str) -> str:
    """Шифрует сообщение перед сохранением в БД"""
    if not message:
        return ""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(message.encode())
    return encrypted.decode()

def decrypt_message(encrypted_message: str) -> str:
    """Расшифровывает сообщение при чтении из БД"""
    if not encrypted_message:
        return ""
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_message.encode())
        return decrypted.decode()
    except Exception as e:
        # Если не удалось расшифровать (старое незашифрованное сообщение)
        print(f"Ошибка расшифровки: {e}")
        return encrypted_message  # Возвращаем как есть