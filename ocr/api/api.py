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
        # Basic setup code remains same until image processing
        doc = frappe.get_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)
        
        if not item:
            return {"success": False, "error": "Item not found."}

        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        file_path = get_file_path(file_url)
        
        # Enhanced image processing specifically for these labels
        with Image.open(file_path) as img:
            # Convert to grayscale
            img = img.convert("L")
            
            # Enhance contrast - these labels are black text on white
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)  # Increased contrast for better text recognition
            
            # Sharpen the image
            img = img.filter(ImageFilter.SHARPEN)
            
            # Resize while maintaining aspect ratio
            img.thumbnail((1200, 1200))  # Increased resolution for better accuracy

        # Configure tesseract for printed text
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789:.()/ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        extracted_text = pytesseract.image_to_string(img, config=custom_config)
        
        # Store raw text for logging
        raw_text = extracted_text

        # More specific patterns based on the sample images
        lot_no = None
        reel_no = None
        weight = None
        missing_fields = []

        # Extract Lot No. - Looking for 6-7 digit numbers after "Lot No."
        lot_pattern = r"Lot\s*No\.\s*:\s*(\d{6,7})"
        lot_match = re.search(lot_pattern, extracted_text, re.IGNORECASE)
        if lot_match:
            lot_no = lot_match.group(1).strip()

        # Extract Reel No. - Looking for pattern like "XXX XXXXX"
        reel_pattern = r"REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})"
        reel_match = re.search(reel_pattern, extracted_text, re.IGNORECASE)
        if reel_match:
            reel_no = reel_match.group(1).replace(" ", "").strip()

        # Extract Weight - Looking for number after "Wt (In Kgs):"
        weight_pattern = r"Wt\s*\(In\s*Kgs\)\s*:\s*(\d+)"
        weight_match = re.search(weight_pattern, extracted_text, re.IGNORECASE)
        if weight_match:
            weight = weight_match.group(1).strip()

        # Fallback patterns if main patterns fail
        if not lot_no:
            # Look for any 6-digit number
            fallback_lot = re.search(r"\b(\d{6})\b", extracted_text)
            if fallback_lot:
                lot_no = fallback_lot.group(1)
            missing_fields.append("Lot No")

        if not reel_no:
            # Look for any 8-9 digit number
            fallback_reel = re.search(r"\b(\d{3}\d{5})\b", extracted_text)
            if fallback_reel:
                reel_no = fallback_reel.group(1)
            missing_fields.append("Reel No")

        if not weight:
            # Look for last number in the text
            fallback_weight = re.search(r".*?(\d+)(?!.*\d)", extracted_text)
            if fallback_weight:
                weight = fallback_weight.group(1)
            missing_fields.append("Weight")

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

        # Log the extracted text for debugging
        frappe.logger().debug(f"Raw OCR Text: {raw_text}")
        frappe.logger().debug(f"Extracted: Lot={lot_no}, Reel={reel_no}, Weight={weight}")

        message = ""
        if missing_fields:
            message = f"Please manually enter the following fields: {', '.join(missing_fields)}"

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text,
            "message": message,
            "missing_fields": missing_fields
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}\nRaw Text: {extracted_text}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
