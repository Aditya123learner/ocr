import json
import re
import frappe
from google.cloud import vision
from frappe.utils.file_manager import get_file_path

@frappe.whitelist()
def extract_item_data_from_document(docname, item_idx, file_url):
    try:
        # Get Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        
        # Convert item_idx to integer
        item_idx = int(item_idx)
        
        # Get the template item and its position
        template_item = None
        template_position = 0
        for i, item in enumerate(doc.items):
            if item.idx == item_idx:
                template_item = item
                template_position = i
                break
                
        if not template_item:
            return {"success": False, "error": "Selected item not found in document"}
            
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
            return {"success": False, "error": "No text detected"}
            
        extracted_text = texts[0].description
        
        # Extract Lot numbers and their positions
        lot_entries = re.finditer(r"Credit.*?(\d{6})", extracted_text, re.IGNORECASE | re.DOTALL)
        lot_positions = [(m.start(), m.group(1)) for m in lot_entries]

        # Extract BSR numbers and weights
        reel_weight_entries = re.finditer(r'(\d{8})\s+(\d{2,3}(?:\.\d{0,2})?)', extracted_text)
        reel_weight_positions = [(m.start(), m.group(1), m.group(2)) for m in reel_weight_entries]

        # Sort positions
        lot_positions.sort()
        reel_weight_positions.sort()

        # Associate Lot No. with BSR No. and weight
        current_lot_no = None
        rows_data = []
        for rw_start, reel_no, weight in reel_weight_positions:
            # Find the latest Lot No. before current BSR No.
            for lot_start, lot_no in lot_positions:
                if lot_start < rw_start:
                    current_lot_no = lot_no
                else:
                    break
            rows_data.append((current_lot_no, reel_no, weight))

        # Store items that come after the template position
        items_after = doc.items[template_position + 1:]
        
        # Remove items from template position onwards
        doc.items = doc.items[:template_position]
        
        # Get template data from the selected item
        template_data = {
            'item_code': template_item.item_code,
            'item_name': template_item.item_name,
            'description': template_item.description,
            'uom': template_item.uom,
            'warehouse': template_item.warehouse,
        }
        
        # Add new rows for each reel number at the template position
        for lot_no, reel_no, weight in rows_data:
            row_data = template_data.copy()
            row_data.update({
                'custom_lot_no': lot_no,
                'custom_reel_no': reel_no,
                'qty': float(weight),
                'received_qty': float(weight),
                'accepted_qty': float(weight),
                'rejected_qty': 0
            })
            doc.append('items', row_data)
        
        # Add back the remaining items
        for item in items_after:
            doc.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'description': item.description,
                'uom': item.uom,
                'warehouse': item.warehouse,
                'custom_lot_no': item.custom_lot_no if hasattr(item, 'custom_lot_no') else None,
                'custom_reel_no': item.custom_reel_no if hasattr(item, 'custom_reel_no') else None,
                'qty': item.qty,
                'received_qty': item.received_qty,
                'accepted_qty': item.accepted_qty,
                'rejected_qty': item.rejected_qty
            })
        
        # Save the document
        doc.save(ignore_version=True)
        
        return {
            "success": True,
            "message": f"Successfully created {len(rows_data)} rows for selected item",
            "rows_count": len(rows_data)
        }
        
    except Exception as e:
        frappe.log_error(f"Item Document OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "Item Document OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
