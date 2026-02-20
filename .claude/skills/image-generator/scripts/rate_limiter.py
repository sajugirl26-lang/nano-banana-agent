#!/usr/bin/env python3
"""API 키 로테이션 + Rate Limit 관리 + Pro/Flash 모델 전환"""
import json
import time
import threading
from pathlib import Path
from datetime import date

CONFIG_DIR = Path(__file__).parents[4] / "config"
API_KEYS_FILE = CONFIG_DIR / "api-keys.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
DAILY_COUNTS_FILE = Path(__file__).parents[4] / "output" / "logs" / "daily_counts.json"


def load_api_config() -> dict:
    with open(API_KEYS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self.config = load_api_config()
        self.keys = self.config.get("keys", [])
        self.global_cfg = self.config.get("global", {})
        settings = load_settings()

        self.min_interval = self.global_cfg.get("min_interval_seconds", 20)
        self.ipm_limit = self.global_cfg.get("ipm_limit", 3)
        self.daily_limit_per_key = self.global_cfg.get("daily_limit_per_key", 40)
        self.max_retry = self.global_cfg.get("max_retry", 3)
        self.cooldown = self.global_cfg.get("cooldown_seconds", 60)
        self.flash_retry_interval = settings.get("session", {}).get("flash_pro_retry_interval", 10)

        self._model_pro = settings.get("model_pro", "gemini-2.0-flash-preview-image-generation")
        self._model_flash = settings.get("model_flash", "gemini-2.0-flash-preview-image-generation")

        self._key_index = 0
        self._last_call_time: dict = {}
        self._daily_counts: dict = {}
        self._rate_limited_until: dict = {}

        self._using_flash = False
        self._flash_count = 0

        self._load_daily_counts()

    def _load_daily_counts(self):
        """파일에서 일일 카운트 로드 (프로세스 재시작 시 복원)"""
        if not DAILY_COUNTS_FILE.exists():
            return
        try:
            with open(DAILY_COUNTS_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            today = str(date.today())
            for ck, info in saved.items():
                if info.get("date") == today:
                    self._daily_counts[ck] = info
        except Exception:
            pass

    def _save_daily_counts(self):
        """일일 카운트를 파일에 저장"""
        try:
            DAILY_COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = DAILY_COUNTS_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._daily_counts, f, ensure_ascii=False)
            tmp.replace(DAILY_COUNTS_FILE)
        except Exception:
            pass

    def _count_key(self, key_id: str) -> str:
        """모델별 분리된 카운트 키 (Pro/Flash 별도 한도)"""
        mode = "flash" if self._using_flash else "pro"
        return f"{key_id}_{mode}"

    def _get_daily_count(self, key_id: str) -> int:
        today = str(date.today())
        ck = self._count_key(key_id)
        if ck not in self._daily_counts or self._daily_counts[ck]["date"] != today:
            self._daily_counts[ck] = {"date": today, "count": 0}
        return self._daily_counts[ck]["count"]

    def _increment_daily(self, key_id: str):
        today = str(date.today())
        ck = self._count_key(key_id)
        if ck not in self._daily_counts or self._daily_counts[ck]["date"] != today:
            self._daily_counts[ck] = {"date": today, "count": 0}
        self._daily_counts[ck]["count"] += 1
        self._save_daily_counts()

    def _is_key_available(self, key: dict) -> bool:
        key_id = key["id"]
        now = time.time()
        if self._rate_limited_until.get(key_id, 0) > now:
            return False
        limit = key.get("daily_limit", self.daily_limit_per_key)
        if self._get_daily_count(key_id) >= limit:
            return False
        last = self._last_call_time.get(key_id, 0)
        if now - last < self.min_interval:
            return False
        return True

    def get_available_key(self) -> dict | None:
        with self._lock:
            n = len(self.keys)
            if n == 0:
                return None
            for _ in range(n):
                key = self.keys[self._key_index % n]
                self._key_index += 1
                if self._is_key_available(key):
                    return key
            return None

    def mark_rate_limited(self, key_id: str):
        with self._lock:
            self._rate_limited_until[key_id] = time.time() + self.cooldown
            print(f"  [429] {key_id} → {self.cooldown}초 쿨다운")

    def mark_used(self, key_id: str):
        with self._lock:
            self._last_call_time[key_id] = time.time()
            self._increment_daily(key_id)

    def all_keys_rate_limited(self) -> bool:
        return all(not self._is_key_available(k) for k in self.keys)

    def switch_to_flash(self) -> bool:
        if not self._using_flash:
            self._using_flash = True
            self._flash_count = 0
            print("[모델 전환] Pro → Flash")
            return True
        return False

    def try_switch_back_to_pro(self) -> bool:
        """Flash 10회마다 Pro 복귀 시도"""
        if not self._using_flash:
            return False
        self._flash_count += 1
        if self._flash_count % self.flash_retry_interval == 0:
            if not self.all_keys_rate_limited():
                self._using_flash = False
                print("[모델 복귀] Flash → Pro")
                return True
        return False

    @property
    def current_model(self) -> str:
        return self._model_flash if self._using_flash else self._model_pro

    @property
    def is_flash_mode(self) -> bool:
        return self._using_flash

    def wait_for_slot(self, timeout: int = 300) -> dict | None:
        """사용 가능한 키가 생길 때까지 대기"""
        start = time.time()
        while time.time() - start < timeout:
            key = self.get_available_key()
            if key:
                return key
            time.sleep(2)
        return None

    def get_total_api_calls(self) -> int:
        """이 세션에서 실제 API 호출한 총 횟수"""
        total = 0
        for ck, info in self._daily_counts.items():
            total += info.get("count", 0)
        return total

    def reload_keys(self):
        """api-keys.json 재로드 (코드 변경 없이 키 추가 지원)"""
        with self._lock:
            self.config = load_api_config()
            self.keys = self.config.get("keys", [])
        print(f"[OK] API 키 재로드: {len(self.keys)}개")


_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
