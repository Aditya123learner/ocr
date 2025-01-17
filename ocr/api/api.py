# import pytesseract
# import re
# import frappe
# from frappe.utils.file_manager import get_file_path
# from PIL import Image


# @frappe.whitelist()
# def extract_item_level_data(docname, item_idx):
#     try:
#         # Fetch the Purchase Receipt document
#         doc = frappe.get_doc("Purchase Receipt", docname)
#         item_idx=int(item_idx)
#         item = next((i for i in doc.items if i.idx == item_idx), None)
        
#         if not item:
#             return {"success": False, "error": "Item not found."}

#          # Log the row being processed
#         frappe.logger().info(f"Processing row: {item_idx} with image: {item.custom_attach_image}")

   
#         # Get the file URL for the image
#         file_url = item.custom_attach_image
#         if not file_url:
#             return {"success": False, "error": "Please upload an image before extracting data."}

#         # Get the file path
#         file_path = get_file_path(file_url)

#         # Optimize the image
#         with Image.open(file_path) as img:
#             img = img.convert("L")  # Convert to grayscale
#             img = img.resize((800, 800))  # Resize for faster OCR processing

        
#         # Extract text using pytesseract
#         extracted_text = pytesseract.image_to_string(img)
#         raw_text = extracted_text

#         # Extract Lot No. (either 4-digit or 6-digit)
#         lot_no_match = re.search(r"Lot\s*No\.?\s*:\s*(\d{4,6})", extracted_text, re.IGNORECASE)
#         lot_no = lot_no_match.group(1) if lot_no_match else None

#         # Extract Reel No. (including spaces within numbers)
#         reel_no_match = re.search(r"Reel\s*No\.?\s*:\s*([\d\s]+)", extracted_text, re.IGNORECASE)
#         reel_no = reel_no_match.group(1).replace(" ", "") if reel_no_match else None
        

#         # Extract Weight (Wt in Kgs)
#         all_numbers = re.findall(r'\d+', extracted_text)  # Extract all numbers from the text
#         if len(all_numbers) > 1:
#             weight = all_numbers[-1]  # Last number as Weight

#         doc = frappe.get_doc("Purchase Receipt", docname)
#         item = next((i for i in doc.items if i.idx == item_idx), None)

#         # Update the item fields
#         item.custom_lot_no = lot_no
#         item.custom_reel_no = reel_no
#         item.qty = weight
        
#           # Ensure Accepted + Rejected Qty matches Received Qty
#         item.received_qty = weight  # Assume full acceptance, adjust as needed
#         item.rejected_qty = 0  # No rejection, adjust as needed
#         doc.save(ignore_version=True)
        
#         return {
#             "success": True,
#             "lot_no": lot_no,
#             "reel_no": reel_no,
#             "qty": weight,
#             "raw_text": raw_text,
#         }
#     except Exception as e:
#         return {"success": False, "error": str(e)}
import pytesseract
import re
import frappe
from frappe.utils.file_manager import get_file_path
from PIL import Image, ImageEnhance, ImageFilter

@frappe.whitelist()
def extract_item_level_data(docname, item_idx):
    try:
        # Fetch the Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)

        if not item:
            return {"success": False, "error": "Item not found."}

        # Log the row being processed
        frappe.logger().info(f"Processing row: {item_idx} with image: {item.custom_attach_image}")

        # Get the file URL for the image
        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        # Get the file path
        file_path = get_file_path(file_url)

        # Optimize the image
        with Image.open(file_path) as img:
            img = img.convert("L")  # Convert to grayscale
            img = img.filter(ImageFilter.SHARPEN)  # Apply sharpening filter
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2)  # Increase contrast
            img = img.resize((800, 800))  # Resize for consistent OCR

        # Extract text using pytesseract
        extracted_text = pytesseract.image_to_string(img)
        raw_text = extracted_text  # Store raw OCR text for fallback checks

        # Helper function for raw text fallback
        def fallback_extract(field_name, primary_pattern, fallback_pattern=None):
            # Try the primary pattern
            match = re.search(primary_pattern, extracted_text, re.IGNORECASE)
            if match:
                return match.group(1).replace(" ", "")  # Remove spaces

            # Try the fallback pattern in raw text
            if fallback_pattern:
                fallback_match = re.search(fallback_pattern, raw_text, re.IGNORECASE)
                if fallback_match:
                    return fallback_match.group(1).replace(" ", "")

            # Log fallback failure
            frappe.logger().warning(f"Could not extract {field_name} with fallback.")
            return None

        # Extract Lot No. (either 4-digit or 6-digit, with fallback)
        lot_no = fallback_extract(
            "Lot No.",
            r"Lot\s*No\.?\s*:\s*(\d{4,6})",
            fallback_pattern=r"\b\d{4,6}\b"  # Fallback: Find first 4-6 digit number in raw text
        )

        # Extract Reel No. (including spaces within numbers, with fallback)
        reel_no = fallback_extract(
            "Reel No.",
            r"Reel\s*No\.?\s*:\s*([\d\s]+)",
            fallback_pattern=r"\b\d{5,}\b"  # Fallback: Find first long number sequence in raw text
        )

        # Extract Weight (Wt in Kgs, with fallback)
        weight_match = re.search(r"Wt\s*\(In\s*Kgs\)\s*:?\s*(\d+)", extracted_text, re.IGNORECASE)
        weight = weight_match.group(1) if weight_match else None
        if not weight:  # Fallback: Use the last detected number in raw text
            all_numbers = re.findall(r"\d+", raw_text)
            weight = all_numbers[-1] if all_numbers else None

        # Update the item fields
        item.custom_lot_no = lot_no
        item.custom_reel_no = reel_no
        item.qty = weight

        # Ensure Accepted + Rejected Qty matches Received Qty
        item.received_qty = weight  # Assume full acceptance, adjust as needed
        item.rejected_qty = 0  # No rejection, adjust as needed
        doc.save(ignore_version=True)

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
