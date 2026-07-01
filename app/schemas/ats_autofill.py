from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.resume import TailoringPreferences


AutofillAction = Literal[
    "fill_text",
    "select_option",
    "choose_radio",
    "manual_upload",
    "manual_review",
    "skip_sensitive",
    "skip_unknown",
]


class AutofillField(BaseModel):
    field_id: str
    selector: str = ""
    tag: str = ""
    input_type: str = ""
    label: str = ""
    name: str = ""
    id_attr: str = ""
    placeholder: str = ""
    aria_label: str = ""
    required: bool = False
    options: list[str] = Field(default_factory=list)
    context: str = ""


class AutofillMatch(BaseModel):
    field: AutofillField
    action: AutofillAction
    answer_key: str = ""
    answer_value: str = ""
    target_option: str = ""
    confidence: float = 0.0
    reason: str = ""


class AutofillPlan(BaseModel):
    source_url: str = ""
    total_fields: int
    fillable_count: int
    manual_count: int
    skipped_count: int
    matches: list[AutofillMatch]


class AutofillPreviewRequest(BaseModel):
    html: str
    apply_plan: dict
    source_url: str = ""


class AutofillContextCandidate(BaseModel):
    company: str = ""
    role: str = ""
    official_url: str = ""
    apply_plan_path: str = ""
    score: float = 0.0


class AutofillContextResponse(BaseModel):
    source: str
    confidence: float
    apply_plan: dict
    matched_apply_plan_path: str = ""
    prepared_apply_plan_path: str = ""
    prepared_packet_folder_path: str = ""
    prepared_resume_path: str = ""
    prepared_resume_docx_path: str = ""
    prepared_resume_html_path: str = ""
    intended_resume_pdf_path: str = ""
    prepared_resume_pdf_path: str = ""
    pdf_rendered: bool = False
    pdf_error: str = ""
    files_written: list[str] = Field(default_factory=list)
    message: str = ""
    candidates: list[AutofillContextCandidate] = Field(default_factory=list)


class AutofillContextRequest(BaseModel):
    url: str = ""
    page_title: str = ""
    page_text: str = ""
    company: str = ""
    role: str = ""
    source: str = "browser_autofill"
    output_root_override: str = "data/outputs/autofill_packets"
    force_prepare: bool = False
    render_pdf: bool = True
    max_page_text_chars: int = Field(default=24000, ge=1000, le=60000)
    tailoring_preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)


class AutofillAutopilotArmRequest(BaseModel):
    url: str = ""
    apply_plan: dict = Field(default_factory=dict)
    apply_plan_path: str = ""
    overwrite: bool = False
    open_browser: bool = True
    expires_minutes: int = Field(default=30, ge=1, le=240)


class AutofillAutopilotArmResponse(BaseModel):
    armed: bool
    task_id: str = ""
    target_url: str = ""
    apply_plan_path: str = ""
    expires_at: str = ""
    opened_browser: bool = False
    message: str = ""


class AutofillAutopilotContextRequest(BaseModel):
    url: str = ""
    page_title: str = ""
    page_text: str = ""


class AutofillAutopilotContextResponse(BaseModel):
    enabled: bool
    task_id: str = ""
    overwrite: bool = False
    apply_plan: dict = Field(default_factory=dict)
    apply_plan_path: str = ""
    message: str = ""


class AutofillAutopilotResultRequest(BaseModel):
    task_id: str = ""
    url: str = ""
    filled_count: int = 0
    total_fields: int = 0
    fillable_count: int = 0
    manual_count: int = 0
    skipped_count: int = 0
    results: list[dict] = Field(default_factory=list)


class AutofillAutopilotResultResponse(BaseModel):
    recorded: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Page watcher ("third eye") — continuous, ATS-agnostic page awareness
# ---------------------------------------------------------------------------

PageType = Literal[
    "job_description",
    "application_form",
    "both",
    "confirmation",
    "other",
]


class WatcherObserveRequest(BaseModel):
    url: str = ""
    page_title: str = ""
    page_text: str = ""
    form_fields: list[AutofillField] = Field(default_factory=list)
    company: str = ""
    role: str = ""
    use_llm: bool = True
    max_page_text_chars: int = Field(default=16000, ge=500, le=40000)


class WatcherJD(BaseModel):
    company: str = ""
    role: str = ""
    location: str = ""
    seniority: str = ""
    sponsorship_note: str = ""
    key_requirements: list[str] = Field(default_factory=list)
    summary: str = ""


class WatcherFieldSuggestion(BaseModel):
    field_id: str
    selector: str = ""
    label: str = ""
    action: AutofillAction
    value: str = ""
    target_option: str = ""
    confidence: float = 0.0
    reason: str = ""
    sensitive: bool = False
    source: str = "heuristic"  # heuristic | claude


class WatcherObserveResponse(BaseModel):
    page_type: PageType
    page_type_confidence: float = 0.0
    engine: str = "heuristic"  # claude | heuristic
    jd: WatcherJD | None = None
    field_suggestions: list[WatcherFieldSuggestion] = Field(default_factory=list)
    fillable_count: int = 0
    manual_count: int = 0
    sensitive_count: int = 0
    message: str = ""
