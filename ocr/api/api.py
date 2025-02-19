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
        
        # Get the template item from current items list
        template_item = next((item for item in doc.items if item.idx == item_idx), None)
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
        rows = []
        for rw_start, reel_no, weight in reel_weight_positions:
            # Find the latest Lot No. before current BSR No.
            for lot_start, lot_no in lot_positions:
                if lot_start < rw_start:
                    current_lot_no = lot_no
                else:
                    break
            rows.append((current_lot_no, reel_no, weight))

        # Get all indices of items with same item_code that haven't been processed yet
        # (items without lot_no or reel_no)
        pending_items = [
            item.idx for item in doc.items 
            if (item.item_code == template_item.item_code and 
                not (item.custom_lot_no or item.custom_reel_no))
        ]
        
        # Calculate how many rows we can fill with current data
        rows_to_process = min(len(rows), len(pending_items))
        
        # Update only the required number of rows
        for i in range(rows_to_process):
            item_to_update = next(
                (item for item in doc.items if item.idx == pending_items[i]), 
                None
            )
            if item_to_update:
                lot_no, reel_no, weight = rows[i]
                item_to_update.custom_lot_no = lot_no
                item_to_update.custom_reel_no = reel_no
                item_to_update.qty = float(weight)
                item_to_update.received_qty = float(weight)
                item_to_update.accepted_qty = float(weight)
                item_to_update.rejected_qty = 0
        
        doc.save(ignore_version=True)
        
        remaining_items = len(pending_items) - rows_to_process
        
        return {
            "success": True,
            "message": f"Successfully processed {rows_to_process} rows for selected item",
            "rows_processed": rows_to_process,
            "remaining_items": remaining_items,
            "remaining_indices": pending_items[rows_to_process:] if remaining_items > 0 else []
        }
        
    except Exception as e:
        frappe.log_error(f"Item Document OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "Item Document OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
