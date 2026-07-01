import json

from app.services.ats_autofill_service import ATSAutofillService


def sample_apply_plan() -> dict:
    return {
        "resume": {
            "tailored_resume_path": "D:\\Educational Documents\\Resumes\\TestCo\\Akhilesh_TestCo.pdf",
            "base_resume_pdf": "D:\\Educational Documents\\Resumes\\Akhilesh_Base.pdf",
        },
        "ats_answer_bank": {
            "candidate": {
                "full_name": "Akhilesh Arunkumar Kumbhar",
                "legal_first_name": "Akhilesh Arunkumar",
                "legal_last_name": "Kumbhar",
                "email": "akhileshkumbhar0405@gmail.com",
                "phone": "+1 (346) 592-3971",
                "city": "Arlington",
                "state": "TX",
                "country": "United States",
                "linkedin_url": "https://www.linkedin.com/in/akhilesh-kumbhar-aak",
                "github_url": "https://github.com/akhileshkumbhar05-ui",
            },
            "work_authorization": {
                "authorized_to_work_us_now": "Yes",
                "requires_sponsorship_now": "No",
                "requires_sponsorship_future": "Yes",
                "current_status": "F1 OPT",
            },
            "preferences": {
                "willing_to_relocate": "Yes",
            },
        },
    }


def test_autofill_detects_common_ats_fields() -> None:
    html = """
    <form>
      <label for="first_name">First Name</label>
      <input id="first_name" name="first_name" />
      <label for="last_name">Last Name</label>
      <input id="last_name" name="last_name" />
      <label for="email">Email Address</label>
      <input id="email" type="email" />
      <label for="phone">Phone Number</label>
      <input id="phone" type="tel" />
      <label for="linkedin">LinkedIn Profile</label>
      <input id="linkedin" />
      <label for="country">Country</label>
      <select id="country"><option></option><option>United States of America</option></select>
      <label for="state">State</label>
      <select id="state"><option></option><option>Texas</option></select>
      <fieldset>
        <legend>Are you legally authorized to work in the United States?</legend>
        <label><input type="radio" name="authorized" value="yes" /> Yes</label>
        <label><input type="radio" name="authorized" value="no" /> No</label>
      </fieldset>
      <fieldset>
        <legend>Will you now or in the future require visa sponsorship?</legend>
        <label><input type="radio" name="sponsorship" value="yes" /> Yes</label>
        <label><input type="radio" name="sponsorship" value="no" /> No</label>
      </fieldset>
      <label for="resume">Resume/CV</label>
      <input id="resume" type="file" />
    </form>
    """

    plan = ATSAutofillService().build_plan_from_html(html, sample_apply_plan())
    by_label = {match.field.label: match for match in plan.matches}

    assert by_label["First Name"].action == "fill_text"
    assert by_label["First Name"].answer_value == "Akhilesh Arunkumar"
    assert by_label["Email Address"].answer_value == "akhileshkumbhar0405@gmail.com"
    assert by_label["LinkedIn Profile"].answer_value.startswith("https://www.linkedin.com")
    assert by_label["Country"].action == "select_option"
    assert by_label["Country"].target_option == "United States of America"
    assert by_label["State"].target_option == "Texas"

    radio_matches = {match.field.name: match for match in plan.matches if match.field.input_type == "radio_group"}
    assert radio_matches["authorized"].action == "choose_radio"
    assert radio_matches["authorized"].target_option == "Yes"
    assert radio_matches["sponsorship"].target_option == "Yes"

    assert by_label["Resume/CV"].action == "manual_upload"
    assert by_label["Resume/CV"].answer_value.endswith("Akhilesh_TestCo.pdf")


def test_autofill_refuses_sensitive_and_ambiguous_fields() -> None:
    html = """
    <form>
      <label for="gender">Gender</label>
      <select id="gender"><option>Male</option><option>Female</option></select>
      <label for="salary">Desired Salary</label>
      <input id="salary" />
      <label for="citizen">Are you a US Citizen?</label>
      <select id="citizen"><option>Yes</option><option>No</option></select>
      <fieldset>
        <legend>Do you require sponsorship?</legend>
        <label><input type="radio" name="ambiguous_sponsor" value="yes" /> Yes</label>
        <label><input type="radio" name="ambiguous_sponsor" value="no" /> No</label>
      </fieldset>
      <label><input type="checkbox" name="certify" /> I certify that this application is accurate</label>
    </form>
    """

    plan = ATSAutofillService().build_plan_from_html(html, sample_apply_plan())
    by_label = {match.field.label: match for match in plan.matches}
    radio_matches = {match.field.name: match for match in plan.matches if match.field.input_type == "radio_group"}

    assert by_label["Gender"].action == "skip_sensitive"
    assert by_label["Desired Salary"].action == "manual_review"
    assert by_label["Are you a US Citizen?"].action == "manual_review"
    assert radio_matches["ambiguous_sponsor"].action == "manual_review"
    assert by_label["I certify that this application is accurate"].action == "manual_review"


def test_context_falls_back_to_application_profile(tmp_path) -> None:
    profile_path = tmp_path / "application_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "candidate": {
                    "full_name": "Akhilesh Arunkumar Kumbhar",
                    "legal_first_name": "Akhilesh Arunkumar",
                    "legal_last_name": "Kumbhar",
                    "email": "akhileshkumbhar0405@gmail.com",
                    "phone": "+1 (346) 592-3971",
                    "city": "Arlington",
                    "state": "TX",
                    "country": "United States",
                    "linkedin_url": "https://www.linkedin.com/in/akhilesh-kumbhar-aak",
                    "github_url": "https://github.com/akhileshkumbhar05-ui",
                },
                "work_authorization": {
                    "authorized_to_work_in_united_states": True,
                    "requires_current_sponsorship": False,
                    "requires_future_sponsorship": True,
                    "current_status": "F1 OPT",
                },
                "preferences": {"willing_to_relocate": True},
                "resume_storage": {"base_resume_pdf": "D:\\Educational Documents\\Resumes\\base.pdf"},
                "automation_boundary": {"allow_final_submit": False},
            }
        ),
        encoding="utf-8",
    )

    service = ATSAutofillService(profile_path=str(profile_path), apply_plan_roots=[str(tmp_path / "packets")])
    context = service.load_context_for_url("https://example.com/jobs/123/apply")

    assert context.source == "profile_fallback"
    assert context.apply_plan["ats_answer_bank"]["candidate"]["city"] == "Arlington"
    assert context.apply_plan["ats_answer_bank"]["candidate"]["state"] == "TX"
    assert context.apply_plan["ats_answer_bank"]["work_authorization"]["requires_sponsorship_now"] == "No"


def test_profile_apply_plan_enriches_job_without_packet(tmp_path) -> None:
    profile_path = tmp_path / "application_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "candidate": {
                    "full_name": "Akhilesh Arunkumar Kumbhar",
                    "legal_first_name": "Akhilesh Arunkumar",
                    "legal_last_name": "Kumbhar",
                    "email": "akhileshkumbhar0405@gmail.com",
                },
                "work_authorization": {
                    "authorized_to_work_in_united_states": True,
                    "requires_current_sponsorship": False,
                    "requires_future_sponsorship": True,
                },
                "preferences": {"willing_to_relocate": True},
                "resume_storage": {"base_resume_pdf": "D:\\Educational Documents\\Resumes\\base.pdf"},
            }
        ),
        encoding="utf-8",
    )
    service = ATSAutofillService(profile_path=str(profile_path), apply_plan_roots=[str(tmp_path / "packets")])

    apply_plan = service.build_profile_apply_plan(
        "https://example.com/apply/123",
        {
            "job_id": "123",
            "company": "ExampleCo",
            "title": "Junior Data Scientist",
            "location": "Remote, United States",
            "source": "pytest",
        },
    )

    assert apply_plan["job"]["company"] == "ExampleCo"
    assert apply_plan["job"]["role"] == "Junior Data Scientist"
    assert apply_plan["job"]["official_url"] == "https://example.com/apply/123"
    assert apply_plan["resume"]["base_resume_pdf"].endswith("base.pdf")
    assert apply_plan["resume"]["tailored_resume_path"] == ""
    assert apply_plan["ats_answer_bank"]["candidate"]["email"] == "akhileshkumbhar0405@gmail.com"


def test_context_matches_existing_apply_plan_by_job_id(tmp_path) -> None:
    profile_path = tmp_path / "application_profile.json"
    profile_path.write_text(json.dumps({"candidate": {}, "work_authorization": {}, "preferences": {}}), encoding="utf-8")
    packet_dir = tmp_path / "packets" / "Thales" / "application_packets" / "20260526_ai_engineer"
    packet_dir.mkdir(parents=True)
    apply_plan_path = packet_dir / "apply_plan.json"
    apply_plan_path.write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "R0210027",
                    "company": "Thales",
                    "role": "Artificial Intelligence Space Engineer",
                    "official_url": "https://careers.thalesgroup.com/global/en/job/R0210027/Artificial-Intelligence-Space-Engineer",
                },
                "ats_answer_bank": sample_apply_plan()["ats_answer_bank"],
            }
        ),
        encoding="utf-8",
    )

    service = ATSAutofillService(profile_path=str(profile_path), apply_plan_roots=[str(tmp_path / "packets")])
    context = service.load_context_for_url("https://careers.thalesgroup.com/global/en/apply/R0210027")

    assert context.source == "matched_apply_plan"
    assert context.confidence > 0.9
    assert context.matched_apply_plan_path == str(apply_plan_path)
    assert context.apply_plan["job"]["company"] == "Thales"


def test_context_does_not_match_wrong_packet_by_role_words_only(tmp_path) -> None:
    profile_path = tmp_path / "application_profile.json"
    profile_path.write_text(json.dumps({"candidate": {}, "work_authorization": {}, "preferences": {}}), encoding="utf-8")
    packet_dir = tmp_path / "packets" / "GumGum" / "application_packets" / "20260528_data_scientist"
    packet_dir.mkdir(parents=True)
    (packet_dir / "apply_plan.json").write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "gumgum-data-scientist",
                    "company": "GumGum",
                    "role": "Data Scientist",
                    "official_url": "https://jobs.example.com/gumgum/data-scientist",
                },
                "ats_answer_bank": sample_apply_plan()["ats_answer_bank"],
            }
        ),
        encoding="utf-8",
    )

    service = ATSAutofillService(profile_path=str(profile_path), apply_plan_roots=[str(tmp_path / "packets")])
    context = service.load_context_for_url("https://careers.otherco.com/jobs/data-scientist/apply")

    assert context.source == "profile_fallback"
