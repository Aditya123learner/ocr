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
import cv2
import numpy as np

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

        # Enhanced image processing
        with Image.open(file_path) as img:
            # Convert to grayscale
            img = img.convert("L")
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)
            # Sharpen image
            img = img.filter(ImageFilter.SHARPEN)
            # Resize
            img.thumbnail((1200, 1200))

        # Convert PIL image to OpenCV format for additional preprocessing
        img_cv = np.array(img)
        img_cv = cv2.adaptiveThreshold(img_cv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        img_cv = cv2.resize(img_cv, (1200, 1200))
        img_pil = Image.fromarray(img_cv)

        # Extract text using pytesseract with retries
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./:()'
        extracted_text = None
        for psm in [6, 11, 3]:  # Retry with different PSM modes
            try:
                custom_config = f'--oem 3 --psm {psm}'
                extracted_text = pytesseract.image_to_string(img_pil, config=custom_config)
                if extracted_text:
                    break
            except Exception as e:
                frappe.logger().warning(f"Error in OCR with PSM {psm}: {str(e)}")

        if not extracted_text:
            return {"success": False, "error": "OCR failed. Unable to extract text from image."}

        raw_text = extracted_text

        # Helper function for fallback extraction
        def fallback_extract(field_name, primary_pattern, fallback_pattern=None):
            match = re.search(primary_pattern, extracted_text, re.IGNORECASE)
            if match:
                return match.group(1).replace(" ", "")
            if fallback_pattern:
                fallback_match = re.search(fallback_pattern, raw_text, re.IGNORECASE)
                if fallback_match:
                    return fallback_match.group(1).replace(" ", "")
            frappe.logger().warning(f"Could not extract {field_name} even with fallback.")
            return None

        # Extract Lot No.
        lot_no = fallback_extract(
            "Lot No.",
            r"Lot\s*No\.\s*:\s*(\d{6,7})",
            fallback_pattern=r"\b\d{6,7}\b"
        )

        # Extract Reel No.
        reel_no = fallback_extract(
            "Reel No.",
            r"Reel\s*No\.\s*:\s*([\d\s]+)",
            fallback_pattern=r"\b\d{5,}\b"
        )

        # Extract Weight
        weight_patterns = [
            r"Wt\s*\(In\s*Kgs\)\s*:\s*(\d{2,3})",
            r"Wt\s*\(\s*In\s*Kgs\s*\)\s*:?\s*(\d+)",
            r".*?Wt.*?:\s*(\d{2,3})",
            r".*?(?:Wt|Weight).*?(\d+)(?:\s*(?:KG|Kgs|kg))?"
        ]
        weight = None
        for pattern in weight_patterns:
            weight_match = re.search(pattern, extracted_text, re.IGNORECASE)
            if weight_match:
                weight = weight_match.group(1).strip()
                if weight and weight != lot_no:
                    break

        # Final fallback for weight
        if not weight or weight == lot_no:
            all_numbers = re.findall(r"\d+", raw_text)
            weight = all_numbers[-1] if all_numbers else None

        # Update document fields
        if lot_no:
            item.custom_lot_no = lot_no
        if reel_no:
            item.custom_reel_no = reel_no
        if weight:
            item.qty = float(weight)
            item.received_qty = float(weight)
            item.rejected_qty = 0

        doc.save(ignore_version=True)

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text,
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else ''}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}

