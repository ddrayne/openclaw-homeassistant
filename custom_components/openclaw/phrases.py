"""Phrases the integration itself speaks, in the language of the request.

These are not the agent's words: they are the holding line, and the short
messages spoken when a request fails or produces nothing. Home Assistant's
translation files only cover the settings screens, so spoken text lives here,
keyed by the language Home Assistant reports for each request.

To add a language, add an entry with every key from ``PHRASES["en"]``;
``tests/test_phrases.py`` fails if one is missing.
"""

from __future__ import annotations

from .const import (
    BACKGROUND_ERROR_PHRASE,
    BACKGROUND_TIMEOUT_PHRASE,
    CONF_HOLDING_PHRASE,
    DEFAULT_HOLDING_PHRASE,
    EMPTY_REPLY_PHRASE,
)

DEFAULT_LANGUAGE = "en"

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "holding": DEFAULT_HOLDING_PHRASE,
        "background_error": BACKGROUND_ERROR_PHRASE,
        "background_timeout": BACKGROUND_TIMEOUT_PHRASE,
        "empty_reply": EMPTY_REPLY_PHRASE,
        "auth": (
            "The gateway token is no longer valid. Please update it in "
            "Settings, Devices and Services, OpenClaw, Configure."
        ),
        "connection": (
            "I'm having trouble connecting to the Gateway. "
            "Please check your configuration."
        ),
        "timeout": "The response took too long. Please try again.",
        "agent_error": (
            "I encountered an error while processing your request. "
            "Please try again."
        ),
        "unexpected": "An unexpected error occurred. Please try again.",
    },
    "de": {
        "holding": "Ich kümmere mich darum und melde mich, sobald es fertig ist.",
        "background_error": "Entschuldigung, bei dieser Anfrage ist ein Problem aufgetreten.",
        "background_timeout": (
            "Das dauert länger als erwartet, deshalb warte ich nicht mehr darauf."
        ),
        "empty_reply": (
            "Ich habe keine Antwort von OpenClaw erhalten. Bitte versuche es noch einmal."
        ),
        "auth": (
            "Das Gateway-Token ist nicht mehr gültig. Bitte aktualisiere es unter "
            "Einstellungen, Geräte und Dienste, OpenClaw, Konfigurieren."
        ),
        "connection": (
            "Ich kann keine Verbindung zum Gateway herstellen. "
            "Bitte überprüfe deine Konfiguration."
        ),
        "timeout": "Die Antwort hat zu lange gedauert. Bitte versuche es noch einmal.",
        "agent_error": (
            "Bei der Bearbeitung deiner Anfrage ist ein Fehler aufgetreten. "
            "Bitte versuche es noch einmal."
        ),
        "unexpected": (
            "Ein unerwarteter Fehler ist aufgetreten. Bitte versuche es noch einmal."
        ),
    },
    "fr": {
        "holding": "Je m'en occupe, je vous préviens dès que c'est terminé.",
        "background_error": "Désolé, cette demande a rencontré un problème.",
        "background_timeout": (
            "Cela prend plus de temps que prévu, j'ai donc arrêté d'attendre."
        ),
        "empty_reply": "Je n'ai pas reçu de réponse d'OpenClaw. Veuillez réessayer.",
        "auth": (
            "Le jeton de la passerelle n'est plus valide. Veuillez le mettre à jour "
            "dans Paramètres, Appareils et services, OpenClaw, Configurer."
        ),
        "connection": (
            "Je n'arrive pas à me connecter à la passerelle. "
            "Veuillez vérifier votre configuration."
        ),
        "timeout": "La réponse a pris trop de temps. Veuillez réessayer.",
        "agent_error": (
            "Une erreur s'est produite lors du traitement de votre demande. "
            "Veuillez réessayer."
        ),
        "unexpected": "Une erreur inattendue s'est produite. Veuillez réessayer.",
    },
    "es": {
        "holding": "Estoy en ello, te aviso cuando esté listo.",
        "background_error": "Lo siento, esa solicitud ha tenido un problema.",
        "background_timeout": (
            "Está tardando más de lo esperado, así que he dejado de esperar."
        ),
        "empty_reply": "No he recibido respuesta de OpenClaw. Inténtalo de nuevo.",
        "auth": (
            "El token de la pasarela ya no es válido. Actualízalo en Ajustes, "
            "Dispositivos y servicios, OpenClaw, Configurar."
        ),
        "connection": (
            "Tengo problemas para conectarme a la pasarela. "
            "Revisa tu configuración."
        ),
        "timeout": "La respuesta ha tardado demasiado. Inténtalo de nuevo.",
        "agent_error": (
            "Se ha producido un error al procesar tu solicitud. Inténtalo de nuevo."
        ),
        "unexpected": "Se ha producido un error inesperado. Inténtalo de nuevo.",
    },
    "it": {
        "holding": "Me ne occupo io, ti avviso appena ho finito.",
        "background_error": "Mi dispiace, quella richiesta ha avuto un problema.",
        "background_timeout": (
            "Ci sta mettendo più del previsto, quindi ho smesso di aspettare."
        ),
        "empty_reply": "Non ho ricevuto risposta da OpenClaw. Riprova.",
        "auth": (
            "Il token del gateway non è più valido. Aggiornalo in Impostazioni, "
            "Dispositivi e servizi, OpenClaw, Configura."
        ),
        "connection": (
            "Non riesco a connettermi al gateway. Controlla la configurazione."
        ),
        "timeout": "La risposta ha richiesto troppo tempo. Riprova.",
        "agent_error": (
            "Si è verificato un errore durante l'elaborazione della richiesta. Riprova."
        ),
        "unexpected": "Si è verificato un errore imprevisto. Riprova.",
    },
    "nl": {
        "holding": "Ik ga ermee aan de slag en laat het weten zodra het klaar is.",
        "background_error": "Sorry, er ging iets mis met dat verzoek.",
        "background_timeout": (
            "Dat duurt langer dan verwacht, dus ik wacht er niet langer op."
        ),
        "empty_reply": "Ik heb geen antwoord van OpenClaw gekregen. Probeer het opnieuw.",
        "auth": (
            "Het gateway-token is niet meer geldig. Werk het bij via Instellingen, "
            "Apparaten en diensten, OpenClaw, Configureren."
        ),
        "connection": (
            "Ik kan geen verbinding maken met de gateway. Controleer je configuratie."
        ),
        "timeout": "Het antwoord duurde te lang. Probeer het opnieuw.",
        "agent_error": (
            "Er is een fout opgetreden bij het verwerken van je verzoek. "
            "Probeer het opnieuw."
        ),
        "unexpected": "Er is een onverwachte fout opgetreden. Probeer het opnieuw.",
    },
    "pl": {
        "holding": "Zajmę się tym i dam znać, gdy będzie gotowe.",
        "background_error": "Przepraszam, z tym poleceniem wystąpił problem.",
        "background_timeout": (
            "Trwa to dłużej, niż się spodziewałem, więc przestałem czekać."
        ),
        "empty_reply": "Nie otrzymałem odpowiedzi od OpenClaw. Spróbuj ponownie.",
        "auth": (
            "Token bramy jest już nieważny. Zaktualizuj go w Ustawieniach, "
            "Urządzenia oraz usługi, OpenClaw, Konfiguruj."
        ),
        "connection": (
            "Mam problem z połączeniem z bramą. Sprawdź konfigurację."
        ),
        "timeout": "Odpowiedź trwała zbyt długo. Spróbuj ponownie.",
        "agent_error": (
            "Podczas przetwarzania polecenia wystąpił błąd. Spróbuj ponownie."
        ),
        "unexpected": "Wystąpił nieoczekiwany błąd. Spróbuj ponownie.",
    },
    "pt-BR": {
        "holding": "Estou cuidando disso e aviso quando terminar.",
        "background_error": "Desculpe, esse pedido teve um problema.",
        "background_timeout": (
            "Está demorando mais do que o esperado, então parei de esperar."
        ),
        "empty_reply": "Não recebi resposta do OpenClaw. Tente novamente.",
        "auth": (
            "O token do gateway não é mais válido. Atualize-o em Configurações, "
            "Dispositivos e serviços, OpenClaw, Configurar."
        ),
        "connection": (
            "Estou com problemas para me conectar ao gateway. "
            "Verifique sua configuração."
        ),
        "timeout": "A resposta demorou demais. Tente novamente.",
        "agent_error": (
            "Ocorreu um erro ao processar seu pedido. Tente novamente."
        ),
        "unexpected": "Ocorreu um erro inesperado. Tente novamente.",
    },
    "sv": {
        "holding": "Jag tar hand om det och säger till när det är klart.",
        "background_error": "Tyvärr, det uppstod ett problem med den förfrågan.",
        "background_timeout": (
            "Det tar längre tid än väntat, så jag har slutat vänta på det."
        ),
        "empty_reply": "Jag fick inget svar från OpenClaw. Försök igen.",
        "auth": (
            "Gateway-token är inte längre giltig. Uppdatera den under "
            "Inställningar, Enheter och tjänster, OpenClaw, Konfigurera."
        ),
        "connection": (
            "Jag har problem med att ansluta till gatewayen. "
            "Kontrollera din konfiguration."
        ),
        "timeout": "Svaret tog för lång tid. Försök igen.",
        "agent_error": (
            "Ett fel uppstod när din förfrågan behandlades. Försök igen."
        ),
        "unexpected": "Ett oväntat fel uppstod. Försök igen.",
    },
    "ja": {
        "holding": "承知しました。終わったらお知らせします。",
        "background_error": "申し訳ありません。そのリクエストで問題が発生しました。",
        "background_timeout": "予想より時間がかかっているため、待機を終了しました。",
        "empty_reply": "OpenClawから応答がありませんでした。もう一度お試しください。",
        "auth": (
            "ゲートウェイのトークンが無効になりました。設定、デバイスとサービス、"
            "OpenClaw、設定から更新してください。"
        ),
        "connection": "ゲートウェイに接続できません。設定を確認してください。",
        "timeout": "応答に時間がかかりすぎました。もう一度お試しください。",
        "agent_error": (
            "リクエストの処理中にエラーが発生しました。もう一度お試しください。"
        ),
        "unexpected": "予期しないエラーが発生しました。もう一度お試しください。",
    },
    "ko": {
        "holding": "처리하고 있어요. 끝나면 알려드릴게요.",
        "background_error": "죄송해요, 요청을 처리하는 중 문제가 발생했어요.",
        "background_timeout": "예상보다 오래 걸려서 더 이상 기다리지 않을게요.",
        "empty_reply": "OpenClaw에서 응답을 받지 못했어요. 다시 시도해 주세요.",
        "auth": (
            "게이트웨이 토큰이 더 이상 유효하지 않아요. 설정, 기기 및 서비스, "
            "OpenClaw, 구성에서 업데이트해 주세요."
        ),
        "connection": "게이트웨이에 연결할 수 없어요. 설정을 확인해 주세요.",
        "timeout": "응답이 너무 오래 걸렸어요. 다시 시도해 주세요.",
        "agent_error": "요청을 처리하는 중 오류가 발생했어요. 다시 시도해 주세요.",
        "unexpected": "예기치 않은 오류가 발생했어요. 다시 시도해 주세요.",
    },
    "zh-Hans": {
        "holding": "好的，我来处理，完成后告诉你。",
        "background_error": "抱歉，这个请求出了点问题。",
        "background_timeout": "这比预期花的时间更长，所以我不再等待了。",
        "empty_reply": "我没有收到 OpenClaw 的回复，请再试一次。",
        "auth": (
            "网关令牌已失效。请在设置、设备与服务、OpenClaw、配置中更新。"
        ),
        "connection": "我无法连接到网关，请检查你的配置。",
        "timeout": "响应时间过长，请再试一次。",
        "agent_error": "处理你的请求时出错了，请再试一次。",
        "unexpected": "发生了意外错误，请再试一次。",
    },
    "zh-Hant": {
        "holding": "好的，我來處理，完成後告訴你。",
        "background_error": "抱歉，這個請求出了點問題。",
        "background_timeout": "這比預期花的時間更長，所以我不再等待了。",
        "empty_reply": "我沒有收到 OpenClaw 的回覆，請再試一次。",
        "auth": (
            "閘道權杖已失效。請在設定、裝置與服務、OpenClaw、設定中更新。"
        ),
        "connection": "我無法連線到閘道，請檢查你的設定。",
        "timeout": "回應時間過長，請再試一次。",
        "agent_error": "處理你的請求時發生錯誤，請再試一次。",
        "unexpected": "發生未預期的錯誤，請再試一次。",
    },
}

_TRADITIONAL_CHINESE_REGIONS = {"tw", "hk", "mo"}


def resolve_language(language: object) -> str:
    """Map a Home Assistant language tag to a key of ``PHRASES``.

    Home Assistant reports tags such as ``de``, ``de-CH``, ``pt-BR``,
    ``zh-CN`` or ``zh-Hant``. Unknown or missing languages use English.
    """
    if not isinstance(language, str) or not language.strip():
        return DEFAULT_LANGUAGE
    parts = language.strip().replace("_", "-").lower().split("-")
    base, rest = parts[0], set(parts[1:])
    if base == "zh":
        if "hant" in rest or rest & _TRADITIONAL_CHINESE_REGIONS:
            return "zh-Hant"
        return "zh-Hans"
    if base == "pt":
        return "pt-BR"
    return base if base in PHRASES else DEFAULT_LANGUAGE


def phrase(key: str, language: object) -> str:
    """Return a built-in phrase in the request's language."""
    return PHRASES[resolve_language(language)][key]


def holding_phrase(config: dict, language: object) -> str:
    """Return the holding phrase: the user's own, else the built-in one.

    A phrase typed under Configure is always used as written. While the
    setting still holds the English default, the built-in phrase for the
    request's language is used instead.
    """
    configured = (config.get(CONF_HOLDING_PHRASE) or "").strip()
    if configured and configured != DEFAULT_HOLDING_PHRASE:
        return configured
    return phrase("holding", language)
