// console.log("Custom Purchase Receipt JS Loaded!");

// frappe.ui.form.on('Purchase Receipt Item', {
//     custom_extract_text_from_sticker: async function(frm, cdt, cdn) {
//         const row = locals[cdt][cdn];
       
        
//         if (!row.custom_attach_image) {
//             frappe.msgprint(__('Please upload an image before extracting data.'));
//             console.log("No image uploaded. Exiting process.");
//             return;
//         }
//         console.log("Image exists. Making API call...");
//         // await frm.save();
//         // await frm.reload_doc();
         
//          // Save the document to ensure the new row is committed
//         //  if (frm.is_dirty()) {
//         //     console.log("Document has unsaved changes. Saving document...");
//         //     try {
//         //         await frm.save(); // Use async/await to wait for save completion
//         //         frappe.ui.form.refresh();
//         //         await frm.reload_doc();
               
//         //         console.log("Document saved successfully.");
//         //     } catch (error) {
//         //         console.error("Error saving document:", error);
//         //         frappe.msgprint(__('Could not save the document. Please try again.'));
//         //         return;
//         //     }
//         // }
       
        
     

// // Now make the API call
//         frappe.call({
//             method: 'ocr.api.api.extract_item_level_data',
//             args: {
//                 docname: frm.doc.name,
//                 item_idx: row.idx // Pass the correct item index
//             },
//             callback: function (r) {
//                 if (r.message.success) {
//                     frappe.msgprint(__('Data extracted successfully!'));
//                     frappe.model.set_value(cdt, cdn, 'custom_lot_no', r.message.lot_no);
//                     frappe.model.set_value(cdt, cdn, 'custom_reel_no', r.message.reel_no);
//                     frappe.model.set_value(cdt, cdn, 'qty', r.message.qty);

//                     // Update dependent fields
//                     frappe.model.set_value(cdt, cdn, 'accepted_qty', r.message.qty);
//                     frappe.model.set_value(cdt, cdn, 'rejected_qty', 0);

//                     console.log("Fields updated successfully.");
//                     frm.reload_doc();
//                 } else {
//                     frappe.msgprint(__('Error: ' + r.message.error));
//                 }
//             }
//         });
//         await frm.reload_doc();
//     }
// });
frappe.ui.form.on('Purchase Receipt', {
    refresh: function(frm) {
        // Add button for filling all rows from document
        frm.add_custom_button(__('Fill All Rows from Document'), function() {
            if (!frm.doc.items || frm.doc.items.length === 0) {
                frappe.msgprint(__('Please add at least one item first.'));
                return;
            }
            
            // Create a dialog for item selection
            let item_options = frm.doc.items
                .filter(item => !item.custom_lot_no && !item.custom_reel_no)
                .map(item => ({
                    value: item.idx,
                    label: `${item.item_code} - ${item.item_name} (Row ${item.idx})`
                }));
                
            if (item_options.length === 0) {
                frappe.msgprint(__('All items have already been processed.'));
                return;
            }

            let d = new frappe.ui.Dialog({
                title: 'Select Item to Process',
                fields: [
                    {
                        label: 'Select Item',
                        fieldname: 'selected_item',
                        fieldtype: 'Select',
                        options: item_options,
                        reqd: 1
                    }
                ],
                primary_action_label: 'Upload Image',
                primary_action(values) {
                    d.hide();
                    // After selecting item, show file uploader
                    new frappe.ui.FileUploader({
                        doctype: 'Purchase Receipt',
                        docname: frm.doc.name,
                        folder: 'Home/Attachments',
                        on_success: (file_doc) => {
                            processItemDocument(frm, values.selected_item, file_doc.file_url);
                        }
                    });
                }
            });
            d.show();
        });
        
        // Add button for generating multiple rows
        frm.add_custom_button(__('Generate Multiple Rows'), function() {
            if (!frm.doc.items || frm.doc.items.length === 0) {
                frappe.msgprint(__('Please add at least one item first.'));
                return;
            }
            
            let d = new frappe.ui.Dialog({
                title: 'Generate Multiple Rows',
                fields: [
                    {
                        label: 'Number of Rows',
                        fieldname: 'num_rows',
                        fieldtype: 'Int',
                        reqd: 1,
                        default: 1
                    }
                ],
                primary_action_label: 'Generate',
                primary_action(values) {
                    generateMultipleRows(frm, values.num_rows);
                    d.hide();
                }
            });
            d.show();
        });
    }
});

// Function to process document for specific item
function processItemDocument(frm, item_idx, file_url) {
    frappe.show_alert({
        message: __('Processing document, please wait...'),
        indicator: 'blue'
    });
    
    frappe.call({
        method: 'ocr.api.api.extract_item_data_from_document',
        args: {
            docname: frm.doc.name,
            item_idx: item_idx,
            file_url: file_url
        },
        callback: function(r) {
            if (r.message.success) {
                let msg = __(`Successfully processed ${r.message.rows_processed} rows`);
                
                // If there are remaining items, add that to the message
                if (r.message.remaining_items > 0) {
                    msg += __(`\nThere are ${r.message.remaining_items} more rows of this item type to process.`);
                }
                
                frappe.show_alert({
                    message: msg,
                    indicator: 'green'
                });
                
                // Reload the document to show updated data
                frm.reload_doc();
                
                // If there are remaining items, ask if user wants to process another image
                if (r.message.remaining_items > 0) {
                    frappe.confirm(
                        __('Would you like to process another image for the remaining rows?'),
                        () => {
                            // Yes - trigger the button click again
                            frm.custom_buttons['Fill All Rows from Document'][0].click();
                        }
                    );
                }
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Error: ' + r.message.error)
                });
            }
        }
    });
}

// Function to generate multiple rows
function generateMultipleRows(frm, numRows) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    // Get the first row as template
    const templateRow = frm.doc.items[0];
    
    // Create specified number of rows
    for (let i = 0; i < numRows; i++) {
        let row = frm.add_child('items', {
            'item_code': templateRow.item_code,
            'item_name': templateRow.item_name,
            'description': templateRow.description,
            'uom': templateRow.uom,
            'warehouse': templateRow.warehouse,
            // Clear the specific fields we want empty in new rows
            'custom_attach_image': '',
            'custom_lot_no': '',
            'custom_reel_no': '',
            'qty': 0,
            'received_qty': 0,
            'accepted_qty': 0,
            'rejected_qty': 0
        });
    }
    
    frm.refresh_field('items');
    frappe.show_alert({
        message: __(`Generated ${numRows} new rows`),
        indicator: 'green'
    });
    
    frm.save()
        .then(() => {
            console.log(`Successfully generated ${numRows} rows`);
        })
        .catch(err => {
            console.error("Error saving document after generating rows:", err);
            frappe.msgprint(__('Error saving document after generating rows.'));
        });
}

// Keep the existing Purchase Receipt Item form events
frappe.ui.form.on('Purchase Receipt Item', {
    custom_attach_image: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.custom_attach_image) {
            frappe.msgprint(__('Please upload an image.'));
            console.log("No image uploaded. Exiting process.");
            return;
        }
        console.log("Image uploaded. Triggering form save...");
        try {
            await frm.save();
            console.log("Form saved successfully. Making API call...");
            
            frappe.call({
                method: 'ocr.api.api.extract_item_level_data',
                args: {
                    docname: frm.doc.name,
                    item_idx: row.idx
                },
                callback: function(r) {
                    if (r.message.success) {
                        frappe.msgprint(__('Data extracted successfully!'));
                        frappe.model.set_value(cdt, cdn, 'custom_lot_no', r.message.lot_no);
                        frappe.model.set_value(cdt, cdn, 'custom_reel_no', r.message.reel_no);
                        frappe.model.set_value(cdt, cdn, 'qty', r.message.qty);
                        frappe.model.set_value(cdt, cdn, 'accepted_qty', r.message.qty);
                        frappe.model.set_value(cdt, cdn, 'rejected_qty', 0);
                        console.log("Fields updated successfully.");
                        frm.refresh_field("items");
                        frm.reload_doc();
                    } else {
                        frappe.msgprint(__('Error: ' + r.message.error));
                    }
                }
            });
        } catch (error) {
            console.error("Error saving form or calling API:", error);
            frappe.msgprint(__('There was an error processing the extraction. Please try again.'));
        }
    }
});
