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
import exifread
from functools import lru_cache
import io
from typing import Tuple, Optional, Dict, Any

@lru_cache(maxsize=100)
def get_cached_doc(doctype: str, docname: str) -> Any:
    return frappe.get_doc(doctype, docname)

def process_image_with_exif(file_path: str) -> Image.Image:
    """Process image with EXIF orientation handling"""
    img = Image.open(file_path)
    
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)  # details=False for faster processing
            if 'Image Orientation' in tags:
                orientation = tags['Image Orientation'].values[0]
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
    except Exception:
        pass  # Continue without orientation if EXIF reading fails
    
    return img

def optimize_image(img: Image.Image) -> Tuple[Image.Image, str]:
    """Optimize image and extract text"""
    # Convert to grayscale
    img = img.convert('L')
    
    # Resize for optimal OCR
    max_size = (1200, 1200)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # Enhance image in single pass
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    
    # Save to memory buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    
    # OCR configuration
    config = '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789:.()/ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    text = pytesseract.image_to_string(buffer, config=config)
    
    return img, text

# Pre-compile regex patterns
PATTERNS = {
    'lot': re.compile(r"Lot\s*No\.\s*:\s*(\d{6,7})", re.IGNORECASE),
    'reel': re.compile(r"REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})", re.IGNORECASE),
    'weight': re.compile(r"Wt\s*\(In\s*Kgs\)\s*:\s*(\d+)", re.IGNORECASE)
}

@frappe.whitelist()
def extract_item_level_data(docname: str, item_idx: str) -> Dict[str, Any]:
    try:
        # Get document with caching
        doc = get_cached_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)
        
        if not item:
            return {"success": False, "error": "Item not found."}

        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        # Process image with EXIF support
        img = process_image_with_exif(get_file_path(file_url))
        img, extracted_text = optimize_image(img)
        
        # Extract data using patterns
        lot_match = PATTERNS['lot'].search(extracted_text)
        reel_match = PATTERNS['reel'].search(extracted_text)
        
        lot_no = lot_match.group(1) if lot_match else None
        reel_no = reel_match.group(1).replace(" ", "") if reel_match else None
        
        # Enhanced weight extraction
        weight = None
        for line in extracted_text.split('\n'):
            if 'Wt' in line or 'KGS' in line.upper():
                numbers = [num for num in re.findall(r'\d+', line)
                          if num != lot_no and (not reel_no or num not in reel_no)]
                if numbers:
                    weight = numbers[-1]
                    break
        
        # Track missing fields
        missing_fields = []
        if not lot_no: missing_fields.append("Lot No")
        if not reel_no: missing_fields.append("Reel No")
        if not weight: missing_fields.append("Weight")
        
        # Batch update document
        if lot_no:
            item.custom_lot_no = lot_no
        if reel_no:
            item.custom_reel_no = reel_no
        if weight:
            item.qty = float(weight)
            item.received_qty = float(weight)
            item.rejected_qty = 0
            
        doc.save(ignore_version=True)

        # Show message for missing fields using frappe.msgprint
        if missing_fields:
            frappe.msgprint(
                msg=f"Please manually enter: {', '.join(missing_fields)}",
                title='Missing Fields',
                indicator='orange'
            )

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "missing_fields": missing_fields
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}", "OCR Processing Error")
        return {"success": False, "error": str(e)}
