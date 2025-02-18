import json
import re
import frappe
from google.cloud import vision
from frappe.utils.file_manager import get_file_path

@frappe.whitelist()
def extract_document_data(docname, file_url):
    try:
        file_path = get_file_path(file_url)
        # Initialize Google Vision client
        google_credentials = json.loads(frappe.conf.get("google_application_credentials"))
        client = vision.ImageAnnotatorClient.from_service_account_info(google_credentials)
        
        # Read the image
        with open(file_path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        
        # Perform OCR
        response = client.text_detection(image=image)
        texts = response.text_annotations
        if not texts:
            return {"success": False, "error": "No text detected."}
            
        extracted_text = texts[0].description
        
        # Get the Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        
        # Extract product sections
        # First, get all lines
        lines = extracted_text.split('\n')
        product_sections = []
        current_section = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            
            # Check if this is a product line (contains CREPE TISSUE)
            if "CREPE TISSUE" in line:
                # If we have a previous section, save it
                if current_section:
                    product_sections.append("\n".join(current_section))
                    current_section = []
                
                # Add product line
                current_section.append(line)
                
                # Add next line if it contains "Credit"
                if "Credit" in next_line:
                    current_section.append(next_line)
                    i += 2
                else:
                    i += 1
                
                # Continue collecting data until next product or end
                while i < len(lines):
                    next_line = lines[i].strip()
                    if "CREPE TISSUE" in next_line:
                        break
                    if next_line:  # Only add non-empty lines
                        current_section.append(next_line)
                    i += 1
                i -= 1  # Adjust for next iteration
            else:
                i += 1
        
        # Add the last section if exists
        if current_section:
            product_sections.append("\n".join(current_section))

        # For debugging
        frappe.log_error(f"Found {len(product_sections)} product sections:\n" + 
                        "\n---SECTION---\n".join(product_sections))
        
        # Process each original item from Purchase Receipt
        new_items = []
        processed_items = set()  # Keep track of processed items

        for item in doc.items:
            # Skip if we've already processed this item description
            if item.description in processed_items:
                continue
                
            # Find matching product section
            matching_section = None
            for section in product_sections:
                # Get the product name from the first two lines of the section
                section_lines = section.split('\n')[:2]
                section_desc = ' '.join(section_lines).strip()
                item_desc = item.description.strip()
                
                # Clean and normalize descriptions for matching
                section_desc = re.sub(r'\s+', ' ', section_desc)
                item_desc = re.sub(r'\s+', ' ', item_desc)
                
                # Log matching attempts for debugging
                frappe.log_error(f"Comparing:\nItem: {item_desc}\nSection: {section_desc}")
                
                if item_desc in section_desc or section_desc in item_desc:
                    matching_section = section
                    break
            
            if matching_section:
                # Extract lot numbers and their positions
                lot_matches = re.finditer(r"(\d{6})\s+\d+\s+(\d{8})\s+(\d+\.?\d*)", matching_section)
                
                # Create new rows for each BSR number
                for match in lot_matches:
                    lot_no = match.group(1)
                    bsr_no = match.group(2)
                    weight = match.group(3)
                    
                    new_row = {
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "description": item.description,
                        "uom": item.uom,
                        "warehouse": item.warehouse,
                        "custom_lot_no": lot_no,
                        "custom_reel_no": bsr_no,
                        "qty": float(weight),
                        "received_qty": float(weight),
                        "accepted_qty": float(weight),
                        "rejected_qty": 0,
                        "purchase_order": item.purchase_order,
                        "purchase_order_item": item.purchase_order_item,
                        "material_request": item.material_request,
                        "material_request_item": item.material_request_item
                    }
                    new_items.append(new_row)
                
                processed_items.add(item.description)
        
        if new_items:
            # Clear existing items
            doc.items = []
            
            # Add all new items
            for row_data in new_items:
                doc.append("items", row_data)
            
            doc.save(ignore_version=True)
            
            return {
                "success": True,
                "message": f"Successfully created {len(new_items)} rows with data",
                "rows_count": len(new_items)
            }
        else:
            return {
                "success": False,
                "error": "No matching products found in the image"
            }
        
    except Exception as e:
        frappe.log_error(f"Document OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "Document OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
