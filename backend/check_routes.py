import sys
sys.path.insert(0, '.')
try:
    from app.routers import excel_import
    routes = [r.path for r in excel_import.router.routes]
    result = "OK: " + str(routes)
except Exception as e:
    result = "ERROR: " + str(e)

with open('C:/Users/lalal/route_check_result.txt', 'w') as f:
    f.write(result)
print(result)
