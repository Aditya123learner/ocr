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
from PIL import Image, ImageEnhance

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
        
        # Open and preprocess image using PIL
        with Image.open(file_path) as img:
            # Convert to grayscale
            img = img.convert('L')
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)
            
            # Resize for better OCR
            img = img.resize((int(img.size[0]*1.5), int(img.size[1]*1.5)), Image.Resampling.LANCZOS)
            
            # Extract text using pytesseract with custom configuration
            custom_config = '--oem 3 --psm 6'
            extracted_text = pytesseract.image_to_string(img, config=custom_config)
            raw_text = extracted_text
        
        # Enhanced regex patterns for camera-captured images
        lot_no_match = re.search(r"[LI]ot\s*[MNn]o\.?\s*:?\s*(\d{4,6})", extracted_text, re.IGNORECASE)
        lot_no = lot_no_match.group(1) if lot_no_match else None
        
        reel_no_match = re.search(r"[RP]EEL\s*[MNn]o\.?\s*:?\s*([\d\s]+)", extracted_text, re.IGNORECASE)
        reel_no = reel_no_match.group(1).replace(" ", "") if reel_no_match else None
        
        # More flexible weight pattern
        weight_patterns = [
            r"[WV]t\s*\(?[I1]n\s*Kgs?\)?\s*:?\s*(\d{1,3})",  # Standard format
            r"[WV]eight\s*:?\s*(\d{1,3})",  # Alternative format
            r"(\d{1,3})\s*[Kk]gs?"  # Last resort pattern
        ]
        
        weight = None
        for pattern in weight_patterns:
            weight_match = re.search(pattern, extracted_text, re.IGNORECASE)
            if weight_match:
                weight = weight_match.group(1)
                break

        if not any([lot_no, reel_no, weight]):
            frappe.logger().error(f"OCR Raw Text: {raw_text}")
            return {"success": False, "error": "Failed to extract required information from image"}
        
        # Update the item fields
        item.custom_lot_no = lot_no
        item.custom_reel_no = reel_no
        item.qty = weight
        
        # Ensure Accepted + Rejected Qty matches Received Qty
        item.received_qty = weight  # Assume full acceptance
        item.rejected_qty = 0  # No rejection
        
        doc.save(ignore_version=True)
        
        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text
        }
        
    except Exception as e:
        frappe.logger().error(f"OCR Error: {str(e)}")
        return {"success": False, "error": str(e)}
