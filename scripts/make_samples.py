"""Generate the synthetic AML/KYC demo corpus in data/samples/.

These are ORIGINAL documents written in the register of real regulatory text.
They are not reproductions of any official publication, and each one carries a
notice saying so. They exist so the repo demos instantly and deterministically:
the acceptance-test question has a known answer on a known page.

For the authentic corpus, run scripts/fetch_samples.py instead.

    pip install reportlab
    python scripts/make_samples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
    )
except ImportError:  # pragma: no cover
    print("reportlab is required: pip install reportlab", file=sys.stderr)
    raise SystemExit(1)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

NOTICE = (
    "SYNTHETIC DEMONSTRATION DOCUMENT. This text was written for the AgentTrace "
    "sample corpus and is not an official publication of any regulator or bank. "
    "Figures and clause numbers are illustrative."
)

# --------------------------------------------------------------------------
# document 1 - a KYC master direction in the RBI register
# --------------------------------------------------------------------------

KYC_DOC = {
    "filename": "rbi_kyc_master_direction.pdf",
    "title": "Master Direction on Know Your Customer (KYC) Norms",
    "subtitle": "Illustrative Direction No. AT/2024-25/01 - Synthetic Sample",
    "sections": [
        (
            "1. Scope and Applicability",
            [
                "This Direction applies to every Regulated Entity (RE), which for the purposes of this "
                "document means scheduled commercial banks, small finance banks, payments banks, "
                "co-operative banks, non-banking financial companies, and all payment system operators "
                "authorised to operate in the domestic market.",
                "Every RE shall frame a KYC policy approved by its Board. The policy shall incorporate, "
                "at a minimum, a Customer Acceptance Policy, a Customer Identification Procedure, "
                "procedures for Monitoring of Transactions, and a documented Risk Management framework.",
                "The Principal Officer designated under this Direction shall be an officer not below the "
                "rank of General Manager, and shall be responsible for ensuring compliance, monitoring "
                "transactions, and sharing information with the Financial Intelligence Unit.",
            ],
        ),
        (
            "2. Definitions",
            [
                "'Customer Due Diligence' (CDD) means identifying the customer, verifying that identity "
                "using reliable and independent source documents, identifying the beneficial owner, and "
                "understanding the purpose and intended nature of the business relationship.",
                "'Occasional Transaction' means a transaction carried out by a person who does not have "
                "an established account-based relationship with the Regulated Entity.",
                "'Politically Exposed Person' (PEP) means an individual who is or has been entrusted with "
                "a prominent public function in India or in a foreign country, including Heads of State, "
                "senior politicians, senior government officials, judicial or military officers, senior "
                "executives of state-owned corporations, and important political party officials.",
                "'Beneficial Owner' means the natural person who ultimately owns or controls a customer, "
                "or the natural person on whose behalf a transaction is being conducted.",
                "'Suspicious Transaction' means a transaction, whether or not made in cash, which to a "
                "person acting in good faith gives rise to a reasonable ground of suspicion that it may "
                "involve proceeds of crime, or appears to have no economic rationale or bona fide purpose.",
            ],
        ),
        (
            "3. Customer Due Diligence Thresholds",
            [
                "Customer Due Diligence shall be carried out in full at the commencement of every "
                "account-based relationship, irrespective of the value of the first transaction.",
                "For occasional transactions carried out by a person who is not an account holder, the "
                "Regulated Entity shall undertake Customer Due Diligence where the amount of a single "
                "transaction, or of several transactions that appear to be linked, is equal to or "
                "exceeds Rupees 50,000. This is referred to in this Direction as the CDD threshold.",
                "Where a transaction falls below the CDD threshold but the Regulated Entity has reason to "
                "believe that the customer has deliberately structured it, or a series of such "
                "transactions, to remain below that threshold, full Customer Due Diligence shall be "
                "carried out regardless of the amount involved.",
                "For all cross-border wire transfers, the Regulated Entity shall obtain and record "
                "complete originator and beneficiary information where the amount is equal to or exceeds "
                "Rupees 50,000. Domestic wire transfers below this amount shall carry, at a minimum, the "
                "originator's account number or a unique transaction reference.",
                "Simplified Due Diligence may be applied to Small Accounts, being accounts where the "
                "aggregate of all credits in a financial year does not exceed Rupees 1,00,000, the "
                "aggregate of all withdrawals and transfers in a month does not exceed Rupees 10,000, and "
                "the balance at any point in time does not exceed Rupees 50,000.",
            ],
        ),
        (
            "4. Officially Valid Documents",
            [
                "An Officially Valid Document (OVD) means the passport, the driving licence, the "
                "Permanent Account Number card, the Voter's Identity Card issued by the Election "
                "Commission, a job card issued by NREGA duly signed by a State Government officer, or a "
                "letter issued by the National Population Register containing name and address details.",
                "Where the OVD furnished by the customer does not contain updated address details, a "
                "utility bill not more than two months old, a property or municipal tax receipt, or a "
                "pension payment order may be accepted as a deemed OVD for the limited purpose of proof "
                "of address, provided the customer submits an updated OVD within three months.",
                "Regulated Entities shall not insist on any document other than those listed above for "
                "the purpose of opening an account, and shall not deny services on the ground that a "
                "customer's address differs from the address on the document furnished.",
            ],
        ),
        (
            "5. Risk Categorisation and Periodic Updation",
            [
                "Every customer shall be categorised as low, medium or high risk, on the basis of the "
                "customer's identity, social and financial status, nature of business activity, "
                "information about the client's business and their location, and the expected pattern of "
                "transactions in the account.",
                "Periodic updation of KYC records shall be carried out at least once every ten years for "
                "low risk customers, once every eight years for medium risk customers, and once every "
                "two years for high risk customers, from the date of opening of the account or the date "
                "of the last KYC updation, whichever is later.",
                "No fresh proof of address or identity shall be sought at the time of periodic updation "
                "where there is no change in the customer's details, and a self-declaration from the "
                "customer through any digital channel shall be sufficient.",
            ],
        ),
        (
            "6. Enhanced Due Diligence",
            [
                "Enhanced Due Diligence shall be applied to all customers categorised as high risk, to "
                "all Politically Exposed Persons and their family members and close associates, to "
                "correspondent banking relationships, and to any business relationship with a person from "
                "a jurisdiction identified as high risk under Section 9 of this Direction.",
                "Enhanced Due Diligence requires, in addition to standard Customer Due Diligence, the "
                "approval of senior management before establishing or continuing the relationship, the "
                "establishment of the source of funds and the source of wealth, and enhanced ongoing "
                "monitoring of the relationship.",
                "In the case of a Politically Exposed Person, the decision to open an account shall be "
                "taken at a level not below that of the Chief Compliance Officer, and shall be recorded "
                "in writing together with the reasons for the decision.",
                "Where a customer is permitted to commence a business relationship before verification is "
                "complete, the verification shall be completed within a period not exceeding thirty days, "
                "failing which the account shall be closed and the balance returned.",
            ],
        ),
        (
            "7. Monitoring, Reporting and Record Retention",
            [
                "Regulated Entities shall exercise ongoing due diligence with respect to every business "
                "relationship and closely examine transactions in order to ensure that they are "
                "consistent with the Regulated Entity's knowledge of the customer, the customer's "
                "business and risk profile, and where necessary the source of funds.",
                "A Suspicious Transaction Report shall be furnished to the Financial Intelligence Unit "
                "not later than seven working days from the date on which the transaction was concluded "
                "to be of a suspicious nature. The internal conclusion shall itself be arrived at within "
                "thirty days of the alert being raised.",
                "A Cash Transaction Report shall be furnished in respect of all cash transactions of a "
                "value exceeding Rupees 10,00,000, and of all series of integrally connected cash "
                "transactions that together exceed that value within one calendar month.",
                "Records of the identity of clients shall be maintained for a period of five years after "
                "the business relationship has ended, and records of all transactions shall be maintained "
                "for a period of five years from the date of the transaction.",
                "No Regulated Entity, and no director, officer or employee of a Regulated Entity, shall "
                "disclose to the customer or to any third party the fact that a Suspicious Transaction "
                "Report has been or is being furnished. This prohibition is absolute and is referred to "
                "as the tipping-off prohibition.",
            ],
        ),
        (
            "8. Penalties for Non-Compliance",
            [
                "Failure to comply with any provision of this Direction shall attract a monetary penalty "
                "of not less than Rupees 10,000 and not more than Rupees 1,00,000 for each failure, "
                "imposed on the Regulated Entity, and separately on the designated Principal Officer "
                "where personal culpability is established.",
                "Where a failure is continuing, an additional penalty of Rupees 5,000 per day may be "
                "levied for each day after the first during which the failure continues.",
                "Repeated failure in respect of the same provision within a period of twelve months shall "
                "be treated as a separate and aggravated contravention, and may additionally attract "
                "restrictions on the opening of new accounts.",
            ],
        ),
        (
            "9. High Risk Jurisdictions",
            [
                "Regulated Entities shall give special attention to business relationships and "
                "transactions with persons from jurisdictions that do not or insufficiently apply "
                "international standards on combating money laundering and the financing of terrorism.",
                "Where such a jurisdiction is subject to a call for counter-measures, the Regulated "
                "Entity shall apply Enhanced Due Diligence proportionate to the risk, and may be directed "
                "to limit or terminate business relationships with persons from that jurisdiction.",
                "The background and purpose of all transactions with persons from such jurisdictions that "
                "have no apparent economic or lawful purpose shall be examined, and written findings "
                "shall be kept available for the supervisor and the auditors for at least five years.",
            ],
        ),
    ],
}

# --------------------------------------------------------------------------
# document 2 - an FATF-style recommendations summary
# --------------------------------------------------------------------------

FATF_DOC = {
    "filename": "fatf_recommendations_summary.pdf",
    "title": "International Standards on Combating Money Laundering",
    "subtitle": "Summary of Recommendations - Synthetic Sample",
    "sections": [
        (
            "Recommendation 1 - Assessing Risks",
            [
                "Countries should identify, assess and understand the money laundering and terrorist "
                "financing risks they face, and should apply a risk-based approach to ensure that "
                "measures to prevent or mitigate those risks are commensurate with the risks identified.",
                "Where higher risks are identified, countries should require financial institutions to "
                "take enhanced measures. Where lower risks are identified, countries may allow simplified "
                "measures, but simplified measures should never be permitted where there is a suspicion "
                "of money laundering or terrorist financing.",
                "Financial institutions should be required to document their risk assessments, keep them "
                "up to date, and have mechanisms to provide the assessment to competent authorities on "
                "request.",
            ],
        ),
        (
            "Recommendation 10 - Customer Due Diligence",
            [
                "Financial institutions should be prohibited from keeping anonymous accounts or accounts "
                "in obviously fictitious names. Customer due diligence measures should be undertaken when "
                "establishing business relations.",
                "Customer due diligence should be undertaken when carrying out occasional transactions "
                "above the applicable designated threshold of USD/EUR 15,000, including situations where "
                "the transaction is carried out in a single operation or in several operations that "
                "appear to be linked.",
                "Customer due diligence should also be undertaken when carrying out occasional "
                "transactions that are wire transfers above USD/EUR 1,000, when there is a suspicion of "
                "money laundering or terrorist financing regardless of any exemption or threshold, and "
                "when the institution has doubts about the veracity or adequacy of previously obtained "
                "customer identification data.",
                "The customer due diligence measures to be taken are: identifying the customer and "
                "verifying that identity using reliable, independent source documents, data or "
                "information; identifying the beneficial owner and taking reasonable measures to verify "
                "that identity; understanding and, as appropriate, obtaining information on the purpose "
                "and intended nature of the business relationship; and conducting ongoing due diligence "
                "on the business relationship throughout its course.",
            ],
        ),
        (
            "Recommendation 11 - Record Keeping",
            [
                "Financial institutions should be required to maintain, for at least five years, all "
                "necessary records on transactions, both domestic and international, so as to enable them "
                "to comply swiftly with information requests from the competent authorities.",
                "Records must be sufficient to permit reconstruction of individual transactions, "
                "including the amounts and types of currency involved, so as to provide, if necessary, "
                "evidence for prosecution of criminal activity.",
                "Financial institutions should be required to keep all records obtained through customer "
                "due diligence measures, account files and business correspondence, and the results of "
                "any analysis undertaken, for at least five years after the business relationship has "
                "ended or after the date of the occasional transaction.",
            ],
        ),
        (
            "Recommendation 12 - Politically Exposed Persons",
            [
                "Financial institutions should be required, in relation to foreign politically exposed "
                "persons, in addition to performing normal customer due diligence measures, to have "
                "appropriate risk management systems to determine whether the customer or the beneficial "
                "owner is a politically exposed person.",
                "Institutions should obtain senior management approval for establishing or continuing "
                "such business relationships, take reasonable measures to establish the source of wealth "
                "and source of funds, and conduct enhanced ongoing monitoring of the relationship.",
                "In relation to domestic politically exposed persons, and persons who are or have been "
                "entrusted with a prominent function by an international organisation, institutions "
                "should be required to take reasonable measures to determine whether a customer or "
                "beneficial owner is such a person, and where the business relationship is of higher "
                "risk, to apply the same enhanced measures.",
                "These requirements should apply to family members and close associates of all types of "
                "politically exposed person.",
            ],
        ),
        (
            "Recommendation 16 - Wire Transfers",
            [
                "Countries should ensure that financial institutions include required and accurate "
                "originator information, and required beneficiary information, on wire transfers and "
                "related messages, and that the information remains with the wire transfer or related "
                "message throughout the payment chain.",
                "Countries should ensure that financial institutions monitor wire transfers for the "
                "purpose of detecting those that lack required originator or beneficiary information, and "
                "take appropriate measures where such information is missing.",
                "For cross-border wire transfers below any applicable de minimis threshold of USD/EUR "
                "1,000, institutions should be required to include the name of the originator and the "
                "beneficiary and an account number or unique transaction reference, although this "
                "information need not be verified for accuracy unless there is a suspicion.",
            ],
        ),
        (
            "Recommendation 20 - Reporting of Suspicious Transactions",
            [
                "If a financial institution suspects, or has reasonable grounds to suspect, that funds "
                "are the proceeds of a criminal activity or are related to terrorist financing, it should "
                "be required by law to report its suspicions promptly to the financial intelligence unit.",
                "The reporting obligation should be a direct mandatory obligation, and any indirect or "
                "implicit obligation to report suspicious transactions, whether by reason of possible "
                "prosecution for a money laundering offence or otherwise, is not acceptable.",
                "The obligation to report applies regardless of the amount of the transaction, and "
                "applies to attempted transactions as well as to completed ones.",
            ],
        ),
        (
            "Recommendation 21 - Tipping-off and Confidentiality",
            [
                "Financial institutions, their directors, officers and employees should be protected by "
                "law from criminal and civil liability for breach of any restriction on disclosure of "
                "information imposed by contract or by any legislative provision, if they report their "
                "suspicions in good faith to the financial intelligence unit.",
                "This protection should apply even if they did not know precisely what the underlying "
                "criminal activity was, and regardless of whether illegal activity actually occurred.",
                "Financial institutions, their directors, officers and employees should be prohibited by "
                "law from disclosing the fact that a suspicious transaction report or related information "
                "is being filed with the financial intelligence unit.",
            ],
        ),
        (
            "Recommendation 24 - Transparency of Legal Persons",
            [
                "Countries should ensure that there is adequate, accurate and timely information on the "
                "beneficial ownership and control of legal persons that can be obtained or accessed "
                "rapidly and efficiently by competent authorities.",
                "Countries should consider measures to facilitate access to beneficial ownership and "
                "control information by financial institutions undertaking the requirements set out in "
                "Recommendations 10 and 22.",
                "Countries should ensure that companies maintain a register of their shareholders or "
                "members, containing the number of shares held by each shareholder and the categories of "
                "shares, and that this information is kept accurate and updated.",
            ],
        ),
    ],
}

# --------------------------------------------------------------------------
# document 3 - an internal bank AML policy
# --------------------------------------------------------------------------

POLICY_DOC = {
    "filename": "sample_bank_aml_policy.pdf",
    "title": "Anti-Money Laundering and Counter-Terrorist Financing Policy",
    "subtitle": "Meridian Commercial Bank - Version 4.2 - Synthetic Sample",
    "sections": [
        (
            "1. Purpose and Governance",
            [
                "This Policy sets out how Meridian Commercial Bank meets its obligations under applicable "
                "anti-money laundering law and the Master Direction on Know Your Customer Norms. It "
                "applies to every business line, every branch, and every employee, contractor and agent "
                "acting on behalf of the Bank.",
                "The Board of Directors owns this Policy and reviews it at least annually. The Chief "
                "Compliance Officer is the designated Principal Officer and reports functionally to the "
                "Board Audit Committee, with a direct right of escalation that does not pass through "
                "business line management.",
                "Every employee completes mandatory AML training within thirty days of joining and "
                "annually thereafter. Staff in customer-facing and transaction monitoring roles complete "
                "an extended curriculum twice a year. Training completion is a condition of the annual "
                "performance rating.",
            ],
        ),
        (
            "2. Customer Acceptance",
            [
                "The Bank shall not open an account where the identity of the applicant cannot be "
                "verified against an Officially Valid Document, where the applicant is unwilling to "
                "disclose the beneficial owner, or where the applicant appears on any sanctions list "
                "applicable to the Bank.",
                "The Bank shall not establish or maintain any relationship with a shell bank, being a "
                "bank incorporated in a jurisdiction in which it has no physical presence and which is "
                "unaffiliated with a regulated financial group.",
                "Accounts in fictitious names, numbered accounts, and anonymous accounts of any kind are "
                "prohibited without exception.",
                "Applications from Politically Exposed Persons, from non-resident customers in high risk "
                "jurisdictions, and from customers in cash-intensive businesses require the written "
                "approval of the Chief Compliance Officer before the account is activated.",
            ],
        ),
        (
            "3. Customer Due Diligence Procedure",
            [
                "For account-based relationships, full Customer Due Diligence is performed before the "
                "first transaction is permitted. For occasional transactions, Customer Due Diligence is "
                "triggered at the regulatory threshold of Rupees 50,000 for a single transaction or for "
                "several transactions that appear to the Bank to be linked.",
                "The Bank applies a conservative internal trigger of Rupees 40,000 for occasional "
                "transactions in branches designated as high risk by the annual risk assessment. This "
                "internal trigger is stricter than the regulatory threshold and does not replace it.",
                "Beneficial ownership is established for every non-individual customer. For a company, "
                "the beneficial owner is the natural person who holds more than ten per cent of the "
                "shares or capital or profits. For a partnership, the threshold is fifteen per cent. For "
                "a trust, the settlor, the trustees, the protector and the beneficiaries are all "
                "identified.",
                "Where no natural person is identified under the ownership tests above, the natural "
                "person holding the position of senior managing official is recorded as the beneficial "
                "owner, and the reason is documented.",
            ],
        ),
        (
            "4. Transaction Monitoring",
            [
                "All transactions are screened by the Bank's automated monitoring system against "
                "behavioural rules calibrated quarterly. Alerts are queued to the Financial Crime "
                "Operations team and must receive a first-level disposition within two business days.",
                "Alerts that are not closed at first level are escalated to a Level 2 analyst, who has "
                "ten business days to reach a documented conclusion. Cases escalated to the Principal "
                "Officer must be concluded within thirty days of the original alert.",
                "The following patterns are configured as mandatory alert triggers: structuring of cash "
                "deposits below the reporting threshold; a sudden increase in account turnover "
                "inconsistent with the declared profile; rapid movement of funds in and out of an account "
                "leaving a negligible balance; and transactions with counterparties in jurisdictions "
                "subject to counter-measures.",
                "Monitoring rule changes require sign-off from both the Chief Compliance Officer and the "
                "Head of Model Risk, and every change is version-controlled with a documented rationale "
                "and a back-test against the preceding six months of transaction data.",
            ],
        ),
        (
            "5. Reporting Obligations",
            [
                "Suspicious Transaction Reports are filed with the Financial Intelligence Unit within "
                "seven working days of the internal conclusion that a transaction is suspicious. The "
                "Principal Officer is the sole authorised signatory for these reports.",
                "Cash Transaction Reports are filed for all cash transactions exceeding Rupees 10,00,000, "
                "and for all series of integrally connected cash transactions exceeding that amount in a "
                "calendar month. These are filed by the fifteenth day of the succeeding month.",
                "Counterfeit Currency Reports are filed for every instance of forged or counterfeit "
                "currency detected, irrespective of value, within seven working days of detection.",
                "Cross-Border Wire Transfer Reports are filed for all incoming and outgoing international "
                "wire transfers where the value exceeds Rupees 5,00,000.",
                "Employees are strictly prohibited from informing a customer, or any person other than "
                "those with an operational need to know, that a report has been filed or that an account "
                "is under review. Breach of this prohibition is treated as gross misconduct.",
            ],
        ),
        (
            "6. Sanctions Screening",
            [
                "Every customer is screened against applicable sanctions lists at onboarding, on every "
                "list update, and on a full portfolio rescreening performed at least monthly. All "
                "outgoing and incoming payments are screened in real time before release.",
                "A confirmed match results in an immediate freeze of the relevant funds or economic "
                "resources, notification to the competent authority within one working day, and a "
                "prohibition on any further transaction without written authority.",
                "Screening thresholds and fuzzy-matching tolerances are reviewed every six months. The "
                "Bank does not reduce a matching tolerance below the level validated in the most recent "
                "independent model validation without Board Audit Committee approval.",
            ],
        ),
        (
            "7. Record Retention and Audit",
            [
                "Customer identification records are retained for five years after the relationship ends. "
                "Transaction records are retained for five years from the date of the transaction. "
                "Records relating to a filed Suspicious Transaction Report are retained for ten years "
                "from the date of filing.",
                "The Internal Audit function performs an independent review of AML controls annually, and "
                "the results are reported directly to the Board Audit Committee without prior review by "
                "the business lines being audited.",
                "An independent external assessment of the Bank's AML programme is commissioned once "
                "every three years, and the findings, together with a dated remediation plan, are placed "
                "before the Board.",
            ],
        ),
        (
            "8. Consequences of Breach",
            [
                "Failure by an employee to follow this Policy is a disciplinary matter and may result in "
                "termination of employment, in addition to any personal liability arising under "
                "applicable law.",
                "Where a control failure results in a regulatory penalty, the Bank conducts a root cause "
                "analysis within forty-five days and reports the findings and the remediation plan to the "
                "Board Audit Committee.",
                "The Bank does not indemnify employees against personal penalties imposed by a regulator "
                "for wilful breach of this Policy.",
            ],
        ),
    ],
}

DOCUMENTS = [KYC_DOC, FATF_DOC, POLICY_DOC]


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Title"], fontName="Times-Bold", fontSize=18, leading=23
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=11,
            leading=15,
            spaceAfter=10,
            alignment=1,
        ),
        "heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=13,
            leading=17,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "BodyJustified",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=10.5,
            leading=15,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
        ),
        "notice": ParagraphStyle(
            "Notice",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=8.5,
            leading=11,
            textColor="#555555",
        ),
    }


def _build(doc_spec: dict, out_dir: Path) -> Path:
    styles = _styles()
    path = out_dir / doc_spec["filename"]
    running_title = doc_spec["title"]

    def decorate(canvas, doc):
        """Header and a real page number footer, so citations are checkable."""
        canvas.saveState()
        canvas.setFont("Times-Italic", 8)
        canvas.setFillColorRGB(0.45, 0.45, 0.45)
        canvas.drawString(20 * mm, A4[1] - 12 * mm, running_title)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
        canvas.line(20 * mm, A4[1] - 14 * mm, A4[0] - 20 * mm, A4[1] - 14 * mm)
        canvas.restoreState()

    template = BaseDocTemplate(
        str(path),
        pagesize=A4,
        title=doc_spec["title"],
        author="AgentTrace synthetic corpus",
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    frame = Frame(
        template.leftMargin,
        template.bottomMargin,
        template.width,
        template.height,
        id="body",
    )
    template.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])

    flow = [
        Paragraph(doc_spec["title"], styles["title"]),
        Paragraph(doc_spec["subtitle"], styles["subtitle"]),
        Paragraph(NOTICE, styles["notice"]),
        Spacer(1, 8 * mm),
    ]
    for index, (heading, paragraphs) in enumerate(doc_spec["sections"]):
        # One section per page keeps page citations meaningful and verifiable.
        if index > 0:
            flow.append(PageBreak())
        flow.append(Paragraph(heading, styles["heading"]))
        for text in paragraphs:
            flow.append(Paragraph(text, styles["body"]))

    template.build(flow)
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in DOCUMENTS:
        path = _build(spec, OUT_DIR)
        print(f"wrote {path.relative_to(OUT_DIR.parent.parent)}  ({path.stat().st_size / 1024:.0f} KB)")
    print(f"\n{len(DOCUMENTS)} sample documents in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
