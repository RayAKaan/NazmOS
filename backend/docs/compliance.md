# NazmOS Compliance Documentation

## Overview

This document outlines the compliance framework for NazmOS, covering GDPR, India's DPDP Act, and SOC2 security controls.

---

## 1. General Data Protection Regulation (GDPR) Compliance

### 1.1 Lawful Basis for Processing

NazmOS processes personal data under the following lawful bases:

| Data Category | Lawful Basis | Purpose |
|--------------|--------------|---------|
| User Account Data | Contract (Art. 6(1)(b)) | Service delivery |
| Usage Analytics | Legitimate Interest (Art. 6(1)(f)) | Service improvement |
| Support Communications | Consent (Art. 6(1)(a)) | Customer support |
| Marketing | Consent (Art. 6(1)(a)) | Product updates |

### 1.2 Data Subject Rights

NazmOS implements the following GDPR rights:

- **Right to Access (Art. 15)**: Users can export all personal data via `/api/users/me/export`
- **Right to Rectification (Art. 16)**: Users can update profile data via `/api/users/me`
- **Right to Erasure (Art. 17)**: Users can request account deletion via `/api/users/me/delete`
- **Right to Data Portability (Art. 20)**: Data exports in JSON/CSV formats
- **Right to Restrict Processing (Art. 18)**: Users can disable marketing communications
- **Right to Object (Art. 21)**: Users can opt out of analytics

### 1.3 Technical Measures

```python
# Data encryption at rest
ENCRYPTION_ALGORITHM = "AES-256-GCM"

# Data encryption in transit
TLS_VERSION = "1.2"  # Minimum TLS 1.2 required

# Data retention policies
USER_DATA_RETENTION_DAYS = 365
AUDIT_LOG_RETENTION_DAYS = 2555  # 7 years for financial data
```

### 1.4 Required Implementations

- [x] Data encryption at rest (AES-256)
- [x] Data encryption in transit (TLS 1.2+)
- [x] Data access logging
- [x] Data export functionality
- [x] Data deletion functionality
- [x] Privacy policy in all supported languages
- [x] Cookie consent mechanism
- [x] Data Processing Agreement (DPA) template

---

## 2. Digital Personal Data Protection (DPDP) Act Compliance (India)

### 2.1 Key Obligations

The DPDP Act, enacted in 2023, imposes specific obligations on data fiduciaries:

| Obligation | Implementation | Status |
|-----------|---------------|--------|
| Purpose Limitation | Collected only for defined purposes | Implemented |
| Data Minimization | Only necessary fields collected | Implemented |
| Consent Mechanism | Explicit opt-in required | Implemented |
| Accuracy | Users can update their data | Implemented |
| Storage Limitation | Data deleted after retention period | Implemented |
| Security Safeguards | Encryption, access controls | Implemented |
| Notice | Clear privacy policy | Implemented |

### 2.2 Significant Data Fiduciary Obligations

If NazmOS is classified as a Significant Data Fiduciary:

- [ ] Data Protection Impact Assessment (DPIA) - Required annually
- [ ] Data Protection Officer (DPO) appointment
- [ ] Independent audit requirement
- [ ] Cross-border data transfer restrictions
- [ ] Additional safeguards for children's data

### 2.3 India-Specific Data Handling

```python
# India-specific configurations
INDIA_DATA_RESIDENCY = True  # Data stored within India
PREFERRED_DATA_CENTER = "ap-south-1"  # AWS Mumbai

# Consent field requirements
CONSENT_FIELDS = {
    "essential": ["account_creation", "inventory_management"],
    "non_essential": ["marketing", "analytics", "third_party_sharing"]
}

# Children data (under 18)
AGE_VERIFICATION = True
PARENTAL_CONSENT_REQUIRED_AGE = 18
```

### 2.4 Consent Management

```python
class ConsentRecord(BaseModel):
    user_id: UUID
    consent_type: str
    purpose: str
    given_at: datetime
    withdrawn_at: Optional[datetime]
    ip_address: str
    user_agent: str
    consent_version: str
```

### 2.5 Breach Notification

Under DPDP Act Section 8:

- **Timeline**: Notify Data Protection Board within 72 hours of becoming aware
- **User Notification**: As soon as practicable
- **Content Requirements**: Nature of breach, type of data, mitigation measures

---

## 3. SOC 2 Compliance

### 3.1 Trust Service Criteria

NazmOS targets compliance with the following Trust Service Criteria:

| Criteria | Description | Implementation |
|----------|-------------|----------------|
| Security | Protection against unauthorized access | WAF, MFA, Encryption |
| Availability | System operational when needed | 99.9% SLA, Redundancy |
| Processing Integrity | Complete, accurate, timely processing | Validation, Error handling |
| Confidentiality | Protected information | Encryption, Access controls |
| Privacy | Personal information protection | GDPR/DPDP compliance |

### 3.2 Security Controls Matrix

#### CC1: Control Environment

- [x] Code of conduct
- [x] Security awareness training
- [x] Background checks
- [x] Organizational structure
- [x] Risk assessment process

#### CC2: Communication and Information

- [x] Security communication channels
- [x] Incident reporting mechanism
- [x] Vendor communication
- [x] Internal reporting

#### CC3: Risk Assessment

- [x] Annual risk assessment
- [x] Vendor risk assessment
- [x] Threat modeling
- [x] Vulnerability scanning

#### CC4: Monitoring Activities

- [x] Continuous monitoring
- [x] Log management
- [x] Anomaly detection
- [x] Periodic review

#### CC5: Control Activities

- [x] Change management
- [x] Segregation of duties
- [x] Access reviews
- [x] Backup and recovery

#### CC6: Logical and Physical Access Controls

- [x] MFA enforcement
- [x] Role-based access control
- [x] Network segmentation
- [x] Physical security (data centers)
- [x] Endpoint security

#### CC7: System Operations

- [x] Performance monitoring
- [x] Capacity management
- [x] Change management
- [x] Incident response

#### CC8: Change Management

- [x] Code review process
- [x] Testing requirements
- [x] Staged deployments
- [x] Rollback procedures

#### CC9: Risk Mitigation

- [x] Vendor management
- [x] Cyber insurance
- [x] Incident response plan
- [x] Business continuity

### 3.3 Evidence Collection

```yaml
# SOC2 Evidence Checklist

Evidence_Collection:
  Access_Management:
    - user_access_review_logs: Q:/logs/access_review/
    - privileged_access_logs: Q:/logs/privileged/
    - termination_checklist: Q:/hr/terminations/
    
  Security_Operations:
    - vulnerability_scans: Q:/security/scans/
    - penetration_test_results: Q:/security/pentest/
    - incident_logs: Q:/security/incidents/
    
  Change_Management:
    - code_review_approvals: Q:/git/approvals/
    - deployment_logs: Q:/ci-cd/deployments/
    - test_results: Q:/ci-cd/tests/
    
  Monitoring:
    - system_logs: Q:/logs/systems/
    - network_flows: Q:/networking/flows/
    - application_logs: Q:/logs/applications/
```

### 3.4 Audit Readiness

```python
# Audit configuration
AUDIT_CONFIG = {
    "log_retention_days": 2555,  # 7 years for SOC2
    "log_immutability": True,
    "log_encryption": True,
    "log_integrity_check": True,
    
    # Key events to log
    "critical_events": [
        "authentication_success",
        "authentication_failure",
        "authorization_change",
        "data_access",
        "data_modification",
        "data_deletion",
        "configuration_change",
        "privilege_escalation",
        "system_event",
        "network_event"
    ],
    
    # Retention by category
    "retention": {
        "application_logs": 365,
        "security_logs": 2555,  # 7 years
        "audit_logs": 2555,
        "database_logs": 2555,
        "system_logs": 365,
        "network_logs": 90
    }
}
```

---

## 4. Security Controls Reference

### 4.1 Encryption Standards

| Data State | Algorithm | Key Length | Implementation |
|-----------|----------|------------|----------------|
| At Rest | AES-256-GCM | 256 bits | Database encryption, File encryption |
| In Transit | TLS 1.2+ | 2048-bit RSA | HTTPS, API communications |
| Key Exchange | ECDHE | P-256 curve | Perfect forward secrecy |
| Hashing | SHA-256 | 256 bits | Passwords, Integrity checks |

### 4.2 Access Control Matrix

```
Role                 | Dashboard | Inventory | Reports | Settings | Admin
---------------------|-----------|-----------|---------|----------|-------
Owner                |    ✓      |    ✓      |    ✓    |    ✓     |   ✓
Manager              |    ✓      |    ✓      |    ✓    |    ✓     |   ✗
Staff                |    ✓      |    R/W    |    R    |    ✗     |   ✗
Accountant          |    ✓      |    ✗      |    ✓    |    ✗     |   ✗
Viewer               |    R      |    R      |    R    |    ✗     |   ✗

Legend: ✓ = Full access, R = Read-only, R/W = Read-write, ✗ = No access
```

### 4.3 Incident Response Timeline

```
Phase              | Timeline     | Actions
-------------------|--------------|----------------------------------
Detection          | T+0         | Automated alerts, User reports
Triage             | T+15min     | Assess severity, Assign team
Containment        | T+30min     | Isolate affected systems
Investigation      | T+1hr       | Root cause analysis
Remediation        | T+4hr       | Fix vulnerability, Patch systems
Recovery           | T+8hr       | Restore services, Verify integrity
Post-Incident      | T+72hr      | Document, Review, Improve
```

---

## 5. Data Processing Addendum (DPA)

### 5.1 Sub-processors

| Processor | Purpose | Country | Safeguards |
|-----------|---------|---------|------------|
| AWS | Cloud Infrastructure | India (Mumbai) | GDPR SCCs, ISO 27001 |
| SendGrid | Transactional Email | USA | DPA, SCCs |
| OpenRouter | Model routing gateway | USA/global provider routing | DPA/vendor review required |
| PagerDuty | Incident Management | USA | DPA |
| Sentry | Error Tracking | USA | DPA |

### 5.2 Standard Contractual Clauses

NazmOS maintains SCCs with all international data processors in accordance with GDPR Article 46.

---

## 6. Compliance Monitoring

### 6.1 Automated Checks

```yaml
compliance_checks:
  daily:
    - data_retention_policy_enforcement
    - consent_expiry_check
    - access_review_reminder
    
  weekly:
    - vulnerability_scan
    - privilege_review
    - backup_verification
    
  monthly:
    - security_training_completion
    - policy_review
    - vendor_assessment
    
  quarterly:
    - penetration_testing
    - disaster_recovery_test
    - compliance_audit
```

### 6.2 Key Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Data Subject Request Resolution | < 30 days | 7 days |
| Security Patch Deployment | < 72 hours | 24 hours |
| Incident Response Time | < 1 hour | 30 minutes |
| Access Review Completion | 100% | 100% |
| Training Completion Rate | 100% | 98% |

---

## 7. Compliance Artifacts

The following documents support compliance demonstration:

1. **Information Security Policy** - `docs/security-policy.md`
2. **Data Classification Policy** - `docs/data-classification.md`
3. **Incident Response Plan** - `docs/incident-response.md`
4. **Business Continuity Plan** - `docs/bcp.md`
5. **Risk Register** - `docs/risk-register.md`
6. **Vendor Assessment Reports** - `docs/vendors/`
7. **Audit Reports** - `docs/audits/`

---

## 8. Contact Information

### Data Protection Officer

For GDPR and DPDP compliance inquiries:
- Email: dpo@nazmos.in
- Address: [Company Legal Address]

### Security Team

For security-related matters:
- Email: security@nazmos.in
- Bug Bounty: https://bugcrowd.com/nazmos

### Compliance Team

For audit and compliance questions:
- Email: compliance@nazmos.in

---

*Document Version: 1.0*  
*Last Updated: 2026-03-29*  
*Next Review Date: 2026-06-29*
