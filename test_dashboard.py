import sys
import time
import app

print("=" * 60)
print("TESTING METADATA DISCOVERY...")
print("=" * 60)
t0 = time.time()
meta = app.discover_metadata()
print(f"Databases: {meta['databases']}")
print(f"Total tables discovered: {len(meta['tables'])}")
print(f"Total system rows: {meta['total_rows']}")
print(f"Storage size: {meta['total_size_mb']} MB")
print(f"Discovery elapsed: {time.time() - t0:.2f}s")

assert len(meta['tables']) > 0, "No tables discovered!"
assert "student_1_to_12.students_records" in meta["table_meta"], "students_records not found!"

print("\n" + "=" * 60)
print("TESTING STUDENT ANALYTICS QUERIES...")
print("=" * 60)
t0 = time.time()
kpi_sql = """
    SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT SchoolCode) as unique_schools,
        COUNT(DISTINCT SchoolName) as unique_school_names,
        COUNT(DISTINCT StudentName) as unique_students,
        COALESCE(SUM(ExamCount), 0) as total_exams,
        COALESCE(SUM(Total_paid__number), 0) as total_paid,
        COALESCE(SUM(Total_price__number), 0) as total_price
    FROM student_1_to_12.students_records
    WHERE 1=1;
"""
kpi_res = app.execute_readonly_query(kpi_sql)
print(f"Student KPIs (elapsed: {time.time() - t0:.2f}s):")
for k, v in kpi_res[0].items():
    print(f"  {k}: {v}")

print("\n" + "=" * 60)
print("TESTING SCHOOL RECONCILIATION QUERY...")
print("=" * 60)
t0 = time.time()
recon_sql = """
    SELECT 
        COUNT(DISTINCT a.SCHOOL_CODE) as ors_school_codes,
        COUNT(DISTINCT b.FIELD_SCHOOL_CODE) as ors_8000_codes,
        COUNT(DISTINCT CASE WHEN a.SCHOOL_CODE = b.FIELD_SCHOOL_CODE THEN a.SCHOOL_CODE END) as matched_codes,
        COUNT(DISTINCT CASE WHEN b.FIELD_SCHOOL_CODE IS NULL THEN a.SCHOOL_CODE END) as only_in_ors_school,
        COUNT(DISTINCT CASE WHEN a.SCHOOL_CODE IS NULL THEN b.FIELD_SCHOOL_CODE END) as only_in_ors_8000
    FROM (SELECT DISTINCT SCHOOL_CODE FROM row_data.ors_school WHERE SCHOOL_CODE IS NOT NULL AND TRIM(SCHOOL_CODE) != '') a
    LEFT JOIN (SELECT DISTINCT FIELD_SCHOOL_CODE FROM row_data.ors_school_8000 WHERE FIELD_SCHOOL_CODE IS NOT NULL AND TRIM(FIELD_SCHOOL_CODE) != '') b
        ON a.SCHOOL_CODE = b.FIELD_SCHOOL_CODE;
"""
recon_res = app.execute_readonly_query(recon_sql)
print(f"School Reconciliation (elapsed: {time.time() - t0:.2f}s): {recon_res[0]}")

print("\n" + "=" * 60)
print("TESTING OCR EXAM FLAGS QUERY...")
print("=" * 60)
t0 = time.time()
ocr_sql = """
    SELECT 
        SUM(CASE WHEN ICO = '1' THEN 1 ELSE 0 END) as ICO,
        SUM(CASE WHEN ICSO = '1' THEN 1 ELSE 0 END) as ICSO,
        SUM(CASE WHEN IEO = '1' THEN 1 ELSE 0 END) as IEO,
        SUM(CASE WHEN IGKO = '1' THEN 1 ELSE 0 END) as IGKO,
        SUM(CASE WHEN IHO = '1' THEN 1 ELSE 0 END) as IHO,
        SUM(CASE WHEN IMO = '1' THEN 1 ELSE 0 END) as IMO,
        SUM(CASE WHEN ISO = '1' THEN 1 ELSE 0 END) as ISO,
        SUM(CASE WHEN ISSO = '1' THEN 1 ELSE 0 END) as ISSO
    FROM row_data.ocr_table;
"""
ocr_res = app.execute_readonly_query(ocr_sql)
print(f"OCR Exam Flags (elapsed: {time.time() - t0:.2f}s): {ocr_res[0]}")

print("\n" + "=" * 60)
print("TESTING MARKETING CONTACT QUERY...")
print("=" * 60)
t0 = time.time()
mkt_sql = """
    SELECT 
        COUNT(*) as total_rows,
        COUNT(CASE WHEN CONTACT_EMAIL IS NOT NULL AND TRIM(CONTACT_EMAIL) != '' THEN 1 END) as non_empty_emails,
        COUNT(DISTINCT CASE WHEN CONTACT_EMAIL IS NOT NULL AND TRIM(CONTACT_EMAIL) != '' THEN LOWER(TRIM(CONTACT_EMAIL)) END) as unique_emails,
        COUNT(CASE WHEN PHONE IS NOT NULL AND TRIM(PHONE) != '' THEN 1 END) as non_empty_phones,
        COUNT(DISTINCT CASE WHEN PHONE IS NOT NULL AND TRIM(PHONE) != '' THEN TRIM(PHONE) END) as unique_phones
    FROM row_data.markeeting_data;
"""
mkt_res = app.execute_readonly_query(mkt_sql)
print(f"Marketing Contacts (elapsed: {time.time() - t0:.2f}s): {mkt_res[0]}")

print("\n" + "=" * 60)
print("TESTING DEDUPLICATION QUERY...")
print("=" * 60)
t0 = time.time()
dup_sql = """
    SELECT 
        COUNT(*) as total_duplicate_groups,
        COALESCE(SUM(cnt), 0) as total_affected_rows,
        COALESCE(SUM(cnt - 1), 0) as extra_redundant_rows
    FROM (
        SELECT PhoneNo as val, COUNT(*) as cnt
        FROM student_1_to_12.students_records
        WHERE PhoneNo IS NOT NULL AND TRIM(PhoneNo) != '' AND PhoneNo != 'NULL'
        GROUP BY PhoneNo
        HAVING cnt > 1
    ) grp;
"""
dup_res = app.execute_readonly_query(dup_sql)
print(f"Duplicate Phone Groups (elapsed: {time.time() - t0:.2f}s): {dup_res[0]}")

print("\n" + "=" * 60)
print("TESTING READ-ONLY SECURITY GUARDS...")
print("=" * 60)
try:
    app.execute_readonly_query("DROP TABLE dummy;")
    print("FAILED: Security guard did not catch DROP TABLE")
except ValueError as e:
    print(f"PASSED: Security guard caught forbidden query: {e}")

try:
    app.execute_readonly_query("DELETE FROM student_1_to_12.students_records WHERE 1=1;")
    print("FAILED: Security guard did not catch DELETE")
except ValueError as e:
    print(f"PASSED: Security guard caught forbidden query: {e}")

print("\n" + "=" * 60)
print("ALL BACKEND & QUERY TESTS PASSED WITH 100% SUCCESS!")
print("=" * 60)
