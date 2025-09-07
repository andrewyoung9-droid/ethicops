import re

html_path = "contact.html"  # Adjust if your file is named differently

# Read the HTML file
with open(html_path, "r", encoding="utf-8") as file:
    content = file.read()

# Replace all @ethicops.gt.tc emails with @ethicops.org
updated_content = re.sub(r'([\w\.-]+)@ethicops\.gt\.tc', r'\1@ethicops.org', content)

# Save the updated file
with open(html_path, "w", encoding="utf-8") as file:
    file.write(updated_content)

print("✅ All email addresses updated to @ethicops.org.")
