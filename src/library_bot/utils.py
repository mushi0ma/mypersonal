import re

def normalize_phone_number(contact: str) -> str:
    """Приводит номер телефона к стандартному формату +7."""
    clean_digits = re.sub(r'\D', '', contact)
    if clean_digits.startswith('8') and len(clean_digits) == 11:
        return '+7' + clean_digits[1:]
    if clean_digits.startswith('7') and len(clean_digits) == 11:
        return '+' + clean_digits
    if re.match(r"^\+\d{1,14}$", contact):
        return contact
    return contact

def get_user_borrow_limit(status: str) -> int:
    """Возвращает лимит книг для пользователя в зависимости от его статуса."""
    return {'студент': 3, 'учитель': 5}.get(status.lower(), 0)