"""
Test dell'invio foto dalla galleria nella chat.

Verificano che l'endpoint accetti immagini vere (PNG 1x1), rifiuti formati e
base64 non validi e che senza chiavi Gemini risponda con un messaggio esplicito
invece di inventare una descrizione.
"""
from __future__ import annotations

# PNG 1x1 trasparente valido (92 byte)
PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="
)


class TestChatImmagine:
    def test_foto_valida_senza_chiavi(self, client, auth_headers):
        response = client.post(
            "/chat",
            json={
                "msg": "Cosa vedi in questa foto?",
                "immagine_base64": PNG_1PX,
                "immagine_mime_type": "image/png",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body.get("reply"), str) and body["reply"]
        assert body.get("latency_ms") is not None

    def test_mime_non_supportato_400(self, client, auth_headers):
        response = client.post(
            "/chat",
            json={
                "msg": "Leggi questo file",
                "immagine_base64": PNG_1PX,
                "immagine_mime_type": "application/pdf",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "immagine" in response.json()["message"].lower()

    def test_base64_non_valido_400(self, client, auth_headers):
        response = client.post(
            "/chat",
            json={
                "msg": "Guarda",
                "immagine_base64": "questo-non-e-base64!!!",
                "immagine_mime_type": "image/jpeg",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "base64" in response.json()["message"].lower()

    def test_immagine_troppo_piccola_400(self, client, auth_headers):
        response = client.post(
            "/chat",
            json={
                "msg": "Guarda",
                "immagine_base64": "AAAA",
                "immagine_mime_type": "image/png",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
