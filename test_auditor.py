from app.services.auditor import audit_url

result = audit_url("https://keenanduplessis.com/")
print(result["flat"]["overall_ai_visibility_score"])
print(result["audit_summary"])
print(result["recommendations"][:2])
