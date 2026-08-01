import re

from pydantic import JsonValue

from agent_runtime.agents.event_extractor.models import (
    EXTRACTOR_VERSION,
    CareEventType,
    ConfidenceBand,
    CreateCareEventCandidateRequestV1,
    EventExtractionContext,
    EventExtractorOutput,
    EventSourceType,
    NoCandidateReason,
    NoEventCandidate,
    ReviewRequirement,
)
from agent_runtime.contracts.models import AgentRunRequest

_MEDICATION_PATTERN = re.compile(
    r"(?:吃藥|服藥|藥(?:吃了|還沒吃|沒吃)|忘(?:了|記)?吃藥|" r"沒(?:有)?吃藥|停藥|改藥|藥量)"
)
_EXPECTED_CONTACT_MISSED_PATTERN = re.compile(
    r"(?:(?:兒子|女兒|家人|朋友|照服員).{0,12}(?:沒來|沒有來|沒打電話|"
    r"沒有打電話|失約)|等.{0,10}(?:沒來|沒有來))"
)
_ACTIVITY_CANCELLED_PATTERN = re.compile(
    r"(?:取消.{0,8}(?:活動|課程|聚會)|(?:不參加|沒參加|無法參加).{0,8}(?:活動|課程|聚會))"
)
_ACTIVITY_PARTICIPATION_PATTERN = re.compile(
    r"(?:(?:參加|去了).{0,8}(?:活動|課程|聚會)|(?:活動|課程|聚會).{0,8}(?:參加|去了))"
)
_MEAL_PATTERN = re.compile(
    r"(?:(?:早餐|午餐|晚餐|早飯|午飯|晚飯).{0,12}(?:吃了|吃過|沒吃|沒有吃|"
    r"不吃|吃不下)|(?:吃了|吃過|沒吃|沒有吃|吃不下).{0,12}"
    r"(?:飯|粥|麵|水果|早餐|午餐|晚餐))"
)
_SLEEP_PATTERN = re.compile(
    r"(?:(?:昨晚|昨天晚上|今天).{0,10}(?:睡得|睡了|失眠|沒睡|睡不著)|" r"睡不好|睡得好|睡不著|失眠)"
)
_SOCIAL_CONTACT_PATTERN = re.compile(
    r"(?:(?:兒子|女兒|家人|朋友|鄰居).{0,12}(?:來看|來訪|打電話|聯絡)|"
    r"(?:來看|來訪|打電話|聯絡).{0,12}(?:兒子|女兒|家人|朋友|鄰居))"
)
_COMPANIONSHIP_PATTERN = re.compile(r"(?:想找人聊天|陪我聊|沒人陪|需要人陪|想要有人陪)")
_EMOTION_PATTERN = re.compile(
    r"我(?:覺得|感到|很)?(?:開心|高興|難過|傷心|孤單|寂寞|擔心|焦慮|害怕)"
)
_ACTIVITY_PATTERN = re.compile(r"(?:散步|運動|做體操|復健運動)")


class EventExtractorAgent:
    """Deterministically produce at most one review-required care event candidate."""

    async def run(
        self,
        request: AgentRunRequest,
        context: EventExtractionContext,
    ) -> EventExtractorOutput:
        if not request.language.lower().startswith("zh"):
            return NoEventCandidate(reason_codes=[NoCandidateReason.UNSUPPORTED_LANGUAGE])

        classification = self._classify(request.input_text.strip())
        if classification is None:
            return NoEventCandidate(reason_codes=[NoCandidateReason.NO_SUPPORTED_EVENT])

        event_type, structured_payload, confidence_band = classification
        return CreateCareEventCandidateRequestV1(
            source_type=EventSourceType.CONVERSATION_SESSION,
            source_id=context.source_id,
            source_version=context.source_version,
            event_type=event_type,
            event_time=context.event_time,
            structured_payload=structured_payload,
            evidence_refs=context.evidence_refs,
            confidence_band=confidence_band,
            review_requirement=ReviewRequirement.REQUIRED,
            extractor_version=EXTRACTOR_VERSION,
        )

    def _classify(
        self, text: str
    ) -> tuple[CareEventType, dict[str, JsonValue], ConfidenceBand] | None:
        if _MEDICATION_PATTERN.search(text):
            return (
                CareEventType.MEDICATION_STATEMENT,
                self._medication_payload(text),
                ConfidenceBand.MEDIUM,
            )
        if _EXPECTED_CONTACT_MISSED_PATTERN.search(text):
            return (
                CareEventType.EXPECTED_CONTACT_MISSED,
                {"observation_basis": "ELDER_STATEMENT", "contact_status": "MISSED"},
                ConfidenceBand.MEDIUM,
            )
        if _ACTIVITY_CANCELLED_PATTERN.search(text):
            return (
                CareEventType.ACTIVITY_CANCELLED,
                {
                    "observation_basis": "ELDER_STATEMENT",
                    "participation_status": "CANCELLED",
                },
                ConfidenceBand.MEDIUM,
            )
        if _ACTIVITY_PARTICIPATION_PATTERN.search(text):
            return (
                CareEventType.ACTIVITY_PARTICIPATION,
                {
                    "observation_basis": "ELDER_STATEMENT",
                    "participation_status": "PARTICIPATED",
                },
                ConfidenceBand.MEDIUM,
            )
        if _MEAL_PATTERN.search(text):
            return CareEventType.MEAL, self._meal_payload(text), ConfidenceBand.MEDIUM
        if _SLEEP_PATTERN.search(text):
            return CareEventType.SLEEP, self._sleep_payload(text), ConfidenceBand.MEDIUM
        if _SOCIAL_CONTACT_PATTERN.search(text):
            return (
                CareEventType.SOCIAL_CONTACT,
                self._social_contact_payload(text),
                ConfidenceBand.MEDIUM,
            )
        if _COMPANIONSHIP_PATTERN.search(text):
            return (
                CareEventType.COMPANIONSHIP_NEED,
                {"observation_basis": "ELDER_STATEMENT", "need_status": "EXPRESSED"},
                ConfidenceBand.MEDIUM,
            )
        if _EMOTION_PATTERN.search(text):
            return (
                CareEventType.EMOTION_EXPRESSION,
                self._emotion_payload(text),
                ConfidenceBand.MEDIUM,
            )
        if _ACTIVITY_PATTERN.search(text):
            return CareEventType.ACTIVITY, self._activity_payload(text), ConfidenceBand.LOW
        return None

    @staticmethod
    def _medication_payload(text: str) -> dict[str, JsonValue]:
        if re.search(r"(?:忘(?:了|記)?吃藥|沒(?:有)?吃藥|藥還沒吃)", text):
            statement_status = "MISSED"
        elif re.search(r"(?:停藥|改藥|藥量)", text):
            statement_status = "CHANGE_MENTIONED"
        elif re.search(r"(?:吃藥了|服藥了|藥吃了)", text):
            statement_status = "TAKEN"
        else:
            statement_status = "MENTIONED"
        return {
            "observation_basis": "ELDER_STATEMENT",
            "statement_status": statement_status,
        }

    @staticmethod
    def _meal_payload(text: str) -> dict[str, JsonValue]:
        if re.search(r"(?:沒吃|沒有吃|不吃|吃不下)", text):
            meal_status = "NOT_CONSUMED"
        elif re.search(r"(?:吃了|吃過)", text):
            meal_status = "CONSUMED"
        else:
            meal_status = "MENTIONED"

        meal_period = "UNSPECIFIED"
        for period, terms in (
            ("BREAKFAST", ("早餐", "早飯")),
            ("LUNCH", ("午餐", "午飯")),
            ("DINNER", ("晚餐", "晚飯")),
        ):
            if any(term in text for term in terms):
                meal_period = period
                break

        return {
            "observation_basis": "ELDER_STATEMENT",
            "meal_status": meal_status,
            "meal_period": meal_period,
        }

    @staticmethod
    def _sleep_payload(text: str) -> dict[str, JsonValue]:
        if re.search(r"(?:睡不好|睡不著|失眠|沒睡)", text):
            sleep_status = "DIFFICULTY_REPORTED"
        elif re.search(r"(?:睡得好|睡了)", text):
            sleep_status = "REST_REPORTED"
        else:
            sleep_status = "MENTIONED"
        return {"observation_basis": "ELDER_STATEMENT", "sleep_status": sleep_status}

    @staticmethod
    def _social_contact_payload(text: str) -> dict[str, JsonValue]:
        if "打電話" in text:
            contact_mode = "PHONE"
        elif re.search(r"(?:來看|來訪)", text):
            contact_mode = "IN_PERSON"
        else:
            contact_mode = "UNSPECIFIED"
        return {
            "observation_basis": "ELDER_STATEMENT",
            "contact_status": "OCCURRED",
            "contact_mode": contact_mode,
        }

    @staticmethod
    def _emotion_payload(text: str) -> dict[str, JsonValue]:
        expressions = (
            ("POSITIVE", ("開心", "高興")),
            ("SAD", ("難過", "傷心")),
            ("LONELY", ("孤單", "寂寞")),
            ("ANXIOUS", ("擔心", "焦慮", "害怕")),
        )
        expression = "MENTIONED"
        for category, terms in expressions:
            if any(term in text for term in terms):
                expression = category
                break
        return {"observation_basis": "ELDER_STATEMENT", "expression": expression}

    @staticmethod
    def _activity_payload(text: str) -> dict[str, JsonValue]:
        activity_kind = "UNSPECIFIED"
        for category, term in (
            ("WALK", "散步"),
            ("EXERCISE", "運動"),
            ("EXERCISE", "做體操"),
            ("REHABILITATION_EXERCISE", "復健運動"),
        ):
            if term in text:
                activity_kind = category
                break
        return {"observation_basis": "ELDER_STATEMENT", "activity_kind": activity_kind}
