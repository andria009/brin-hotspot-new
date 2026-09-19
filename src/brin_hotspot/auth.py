from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from brin_hotspot.config import Settings

ROLES = ("explorer", "mage", "sage", "god")


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    display_name: str
    role: str | None


@lru_cache(maxsize=8)
def jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def decode_access_token(token: str, settings: Settings) -> Identity:
    if not settings.oidc_issuer or not settings.oidc_jwks_url:
        raise HTTPException(status_code=503, detail="Hotspot OIDC is not configured")
    try:
        signing_key = jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Keycloak token") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Keycloak signing keys are unavailable"
        ) from exc
    if claims.get("azp") != settings.oidc_client_id:
        raise HTTPException(status_code=401, detail="Token was issued to another client")
    roles = application_roles(claims, settings.oidc_client_id)
    return Identity(
        subject=str(claims["sub"]),
        email=str(claims.get("email") or ""),
        display_name=str(claims.get("name") or claims.get("preferred_username") or ""),
        role=next((role for role in reversed(ROLES) if role in roles), None),
    )


def application_roles(claims: dict, client_id: str) -> set[str]:
    access = claims.get("resource_access")
    if not isinstance(access, dict) or not isinstance(access.get(client_id), dict):
        return set()
    roles = access[client_id].get("roles")
    return {str(role) for role in roles if str(role) in ROLES} if isinstance(roles, list) else set()


async def access_management_request(
    settings: Settings,
    token: str,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    if not settings.access_management_url:
        raise HTTPException(status_code=503, detail="Access Management is not configured")
    try:
        async with httpx.AsyncClient(
            base_url=settings.access_management_url.rstrip("/"), timeout=10
        ) as client:
            response = await client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Access Management unavailable: {exc}"
        ) from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()
