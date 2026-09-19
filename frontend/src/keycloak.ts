import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? "https://geomimo-keycloak.brin.go.id",
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "brin-geospatial",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "hotspot-new"
});

let initialization: Promise<boolean> | null = null;

export function initializeAuthentication() {
  initialization ??= keycloak.init({
    onLoad: "check-sso",
    pkceMethod: "S256",
    checkLoginIframe: false,
    redirectUri: `${window.location.origin}/auth/callback`
  });
  return initialization;
}

export function login() {
  return keycloak.login({ redirectUri: `${window.location.origin}/auth/callback` });
}

export function register() {
  return keycloak.register({ redirectUri: `${window.location.origin}/auth/callback` });
}

export function logout() {
  return keycloak.logout({ redirectUri: `${window.location.origin}/` });
}

export async function accessToken() {
  if (!keycloak.authenticated) {
    return "";
  }
  await keycloak.updateToken(30);
  return keycloak.token ?? "";
}

export function tokenProfile() {
  return {
    name: String(keycloak.tokenParsed?.name ?? keycloak.tokenParsed?.preferred_username ?? ""),
    email: String(keycloak.tokenParsed?.email ?? "")
  };
}
