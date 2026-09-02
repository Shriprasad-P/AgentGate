from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration."""
    
    database_url: str = "sqlite:///./agentgate.db"
    gateway_token: str = "dev-token-change-me"
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
