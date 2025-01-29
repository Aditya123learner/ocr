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

        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        file_path = get_file_path(file_url)
        
        # 🔹 Enhanced Image Processing for Camera Captured Images
        with Image.open(file_path) as img:
            img = img.convert("L")  # Convert to grayscale
            img = img.filter(ImageFilter.MedianFilter(size=3))  # Reduce noise
            img = img.filter(ImageFilter.SHARPEN)  # Sharpen the text
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)  # Boost contrast for better OCR
            img = img.resize((1200, 1200))  # Resize for consistent OCR accuracy

        # Configure Tesseract for printed text OCR
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789:.()/ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        
        # Extract words and clean empty ones
        words = [w.strip() for w in ocr_data['text'] if w.strip()]
        
        lot_no, reel_no, weight = None, None, None
        
        # Loop through words to find key data
        for i, word in enumerate(words):
            if "Lot" in word and i + 1 < len(words):
                lot_no = words[i + 1] if words[i + 1].isdigit() else None
            if "REEL" in word and i + 1 < len(words):
                reel_no = words[i + 1].replace(" ", "") if words[i + 1].isdigit() else None
            if "Wt" in word or "Kgs" in word:
                weight = words[i + 1] if words[i + 1].isdigit() else None

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

        # Log extracted details
        frappe.logger().debug(f"Extracted: Lot={lot_no}, Reel={reel_no}, Weight={weight}")

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
