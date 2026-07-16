import re
import json
from typing import Tuple, List
from pathlib import Path
import hashlib
import math


class PasswordValidator:
    """Validates password strength according to security best practices."""
    
    COMMON_PASSWORDS = {
        "password", "123456", "123456789", "12345678", "12345", "1234567",
        "password1", "1234567890", "qwerty", "abc123", "monkey", "master",
        "dragon", "letmein", "login", "admin", "welcome", "shadow", "sunshine",
        "princess", "football", "baseball", "iloveyou", "trustno1", "hunter",
        "michael", "jennifer", "jessica", "thomas", "daniel", "hello",
        "superman", "ninja", "mustang", "password123", "password1234",
    }
    
    def __init__(self):
        self.min_length = 10
        self.max_length = 128
    
    def validate(self, password: str, user_context: dict = None) -> Tuple[bool, List[str]]:
        """
        Validate password strength.
        
        Args:
            password: The password to validate
            user_context: Optional context (email, name, business_name) to check against
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not password:
            return False, ["Password is required"]
        
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters")
        
        if len(password) > self.max_length:
            errors.append(f"Password must be less than {self.max_length} characters")
        
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one number")
        
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?\\|`~]', password):
            errors.append("Password must contain at least one special character")
        
        password_lower = password.lower()
        if password_lower in self.COMMON_PASSWORDS:
            errors.append("Password is too common. Choose a more unique password")

        for common in self.COMMON_PASSWORDS:
            if password_lower.startswith(common) and password_lower != common:
                errors.append("Password is too common. Choose a more unique password")
                break
        
        repeated_patterns = [
            r'(.)\1{2,}',  # Same character 3+ times
            r'(0123|1234|2345|3456|4567|5678|6789|7890)',  # Sequential numbers
            r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)',  # Sequential letters
        ]
        for pattern in repeated_patterns:
            if re.search(pattern, password_lower):
                errors.append("Password contains repeated or sequential patterns")
                break
        
        if user_context:
            email = user_context.get('email', '').lower()
            if email:
                email_username = email.split('@')[0].lower()
                if email_username in password_lower:
                    errors.append("Password cannot contain your email username")
            
            name = user_context.get('name', '').lower()
            if name:
                name_parts = [p for p in name.split() if len(p) > 2]
                for part in name_parts:
                    if part in password_lower:
                        errors.append("Password cannot contain your name")
                        break
            
            business_name = user_context.get('business_name', '').lower()
            if business_name:
                if business_name in password_lower:
                    errors.append("Password cannot contain your business name")
            
            years = ['2020', '2021', '2022', '2023', '2024', '2025']
            for year in years:
                if year in password:
                    errors.append("Password cannot contain current or recent years")
                    break
        
        entropy = self._calculate_entropy(password)
        if entropy < 50:
            errors.append("Password is not complex enough")
        
        return len(errors) == 0, errors
    
    def _calculate_entropy(self, password: str) -> float:
        """Calculate password entropy in bits."""
        if not password:
            return 0
        
        charset_size = 0
        if re.search(r'[a-z]', password):
            charset_size += 26
        if re.search(r'[A-Z]', password):
            charset_size += 26
        if re.search(r'\d', password):
            charset_size += 10
        if re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?\\|`~]', password):
            charset_size += 32
        
        if charset_size == 0:
            return 0
        
        entropy = len(password) * math.log2(charset_size)
        return entropy


class InputSanitizer:
    """Sanitizes user input to prevent injection attacks."""
    
    DANGEROUS_PATTERNS = {
        'sql_injection': [
            r"(\b(union|select|insert|update|delete|drop|alter|create|truncate|exec|execute)\b)",
            r"(\b(or|and)\b.*=)",
            r"(--|#|/\*)",
            r"(;|\|\||&&)",
            r"(0x[0-9a-f]+)",
        ],
        'command_injection': [
            r'[;&|`$]',
            r'\b(cat|ls|dir|rm|mv|cp|wget|curl|nc|bash|sh)\b',
            r'(\|\s*\w+)',
        ],
        'path_traversal': [
            r'\.\.[/\\]',
            r'%2e%2e',
            r'\.\.%2f',
            r'([/\\]\.[\.])',
        ],
    }
    
    def __init__(self):
        self.compiled_patterns = {}
        for name, patterns in self.DANGEROUS_PATTERNS.items():
            self.compiled_patterns[name] = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def sanitize_string(self, value: str, max_length: int = 1000) -> str:
        """Sanitize a generic string input."""
        if not isinstance(value, str):
            return str(value)
        
        value = value.strip()
        
        if len(value) > max_length:
            value = value[:max_length]
        
        value = self._remove_null_bytes(value)
        value = self._normalize_whitespace(value)

        # Defense in depth: neutralize common shell metacharacters in generic strings.
        value = re.sub(r'[;&|`$]', '', value)
        value = re.sub(r'\b(cat|ls|dir|rm|mv|cp|wget|curl|nc|bash|sh)\b', '[cmd]', value, flags=re.IGNORECASE)

        return value
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to prevent path traversal."""
        if not filename:
            return "unnamed"
        
        filename = Path(filename).name
        
        filename = re.sub(r'[^\w\s\-\.]', '', filename)
        
        filename = re.sub(r'\.\.+', '.', filename)
        
        if not filename or filename == '.':
            return "unnamed"
        
        max_length = 255
        if len(filename) > max_length:
            name, ext = Path(filename).stem, Path(filename).suffix
            ext = ext[:10]
            name = name[:max_length - len(ext) - 1]
            filename = f"{name}{ext}"
        
        return filename
    
    def sanitize_sql_input(self, value: str) -> str:
        """Sanitize input intended for SQL queries (defense in depth)."""
        if not value:
            return value
        
        value = self.sanitize_string(value)
        
        value = value.replace("'", "''")
        value = value.replace("\\", "\\\\")
        
        return value
    
    def check_sql_injection(self, value: str) -> bool:
        """Check if a value contains potential SQL injection patterns."""
        if not value:
            return False
        
        for pattern in self.compiled_patterns.get('sql_injection', []):
            if pattern.search(value):
                return True
        return False
    
    def check_path_traversal(self, value: str) -> bool:
        """Check if a value contains path traversal patterns."""
        if not value:
            return False
        
        for pattern in self.compiled_patterns.get('path_traversal', []):
            if pattern.search(value):
                return True
        return False
    
    def sanitize_html(self, value: str) -> str:
        """Sanitize HTML content by removing dangerous tags and attributes."""
        if not value:
            return value
        
        dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'style']
        for tag in dangerous_tags:
            value = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', value, flags=re.IGNORECASE | re.DOTALL)
            value = re.sub(f'<{tag}[^>]*/?>', '', value, flags=re.IGNORECASE)
        
        # Remove event handlers (quoted or unquoted), inline style, and script URLs.
        value = re.sub(r'\s+on\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', value, flags=re.IGNORECASE)
        value = re.sub(r'\s+style\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', value, flags=re.IGNORECASE)

        value = value.replace('javascript:', '')
        value = value.replace('data:', '')
        value = value.replace('vbscript:', '')
        
        return value
    
    def _remove_null_bytes(self, value: str) -> str:
        """Remove null bytes that can truncate strings."""
        return value.replace('\x00', '').replace('\u0000', '')
    
    def _normalize_whitespace(self, value: str) -> str:
        """Normalize whitespace to prevent bypasses."""
        value = re.sub(r'[\t\n\r\x0b\x0c]', ' ', value)
        value = re.sub(r' +', ' ', value)
        return value.strip()


class PIIMasker:
    """Masks personally identifiable information for logging and display."""
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone number, showing only last 4 digits."""
        if not phone:
            return phone
        
        digits = re.sub(r'\D', '', phone)
        if len(digits) < 4:
            return '*' * len(digits)
        
        return '*' * (len(digits) - 4) + digits[-4:]
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email address, showing first 2 chars and domain."""
        if not email or '@' not in email:
            return '***'
        
        local, domain = email.split('@', 1)
        
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[:2] + '*' * (len(local) - 2)
        
        return f"{masked_local}@{domain}"
    
    @staticmethod
    def mask_vat(vat: str) -> str:
        """Mask Saudi 15-digit VAT number, showing first 3 and last 3 digits."""
        if not vat or len(vat) < 6:
            return '****'
        return vat[:3] + '*' * (len(vat) - 6) + vat[-3:]
    
    @staticmethod
    def mask_national_id_or_iqama(nid: str) -> str:
        """Mask Saudi National ID or Iqama, showing only last 4 digits."""
        if not nid:
            return nid
        digits = re.sub(r'\D', '', nid)
        if len(digits) < 4:
            return '*' * len(digits)
        return '*' * (len(digits) - 4) + digits[-4:]
    
    @staticmethod
    def mask_address(address: str, keep_chars: int = 10) -> str:
        """Mask address, keeping first and last few characters."""
        if not address:
            return address
        if len(address) <= keep_chars * 2:
            return address[:keep_chars] + '***' + address[-keep_chars:]
        return address[:keep_chars] + '***' + address[-keep_chars:]
    

    @staticmethod
    def mask_pan(pan: str) -> str:
        """Compatibility helper: mask legacy PAN-like identifiers."""
        if not pan or len(pan) < 4:
            return '****'
        return pan[:2] + '*' * max(1, len(pan) - 4) + pan[-2:]

    @staticmethod
    def mask_gstin(gstin: str) -> str:
        """Compatibility helper: mask legacy GSTIN-like identifiers."""
        if not gstin or len(gstin) < 5:
            return '****'
        return gstin[:2] + '*' * max(1, len(gstin) - 5) + gstin[-3:]

    @staticmethod
    def mask_aadhaar(aadhaar: str) -> str:
        """Compatibility helper: mask 12-digit national identifiers."""
        digits = re.sub(r'\D', '', aadhaar or '')
        if len(digits) < 4:
            return '*' * len(digits)
        return '*' * max(0, len(digits) - 4) + digits[-4:]

    @classmethod
    def mask_dict(cls, data: dict, fields_to_mask: List[str] = None) -> dict:
        """Mask KSA PDPL / PII fields in a dictionary."""
        if fields_to_mask is None:
            fields_to_mask = ['phone', 'email', 'vat', 'cr_number', 'national_id', 'iqama', 'address', 'iban']
        
        masked = data.copy()
        for key in list(masked.keys()):
            if any(field in key.lower() for field in fields_to_mask):
                value = masked[key]
                if isinstance(value, str):
                    if 'phone' in key.lower():
                        masked[key] = cls.mask_phone(value)
                    elif 'email' in key.lower():
                        masked[key] = cls.mask_email(value)
                    elif 'vat' in key.lower():
                        masked[key] = cls.mask_vat(value)
                    elif any(k in key.lower() for k in ['national_id', 'iqama', 'cr_number']):
                        masked[key] = cls.mask_national_id_or_iqama(value)
                    elif 'address' in key.lower():
                        masked[key] = cls.mask_address(value)
        
        return masked


password_validator = PasswordValidator()
input_sanitizer = InputSanitizer()
pii_masker = PIIMasker()
