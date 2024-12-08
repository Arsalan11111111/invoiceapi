from odoo import models, fields, api
import qrcode
import base64
from io import BytesIO


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_hexa = fields.Char(string="Invoice Hexa")
    qr_code = fields.Binary(string="QR Code", compute="_compute_qr_code")
    file_no = fields.Char("File Number")

    invoice_base64 = fields.Char(string="Invoice Base64")
    decoded_invoice_base64 = fields.Text(
        string="Decoded Invoice Base64", compute="_compute_decoded_invoice_base64"
    )

    @api.depends('invoice_base64')
    def _compute_decoded_invoice_base64(self):
        for record in self:
            if record.invoice_base64:
                try:
                    # Decode the Base64 string
                    decoded_content = base64.b64decode(record.invoice_base64).decode('utf-8')
                    record.decoded_invoice_base64 = decoded_content
                except Exception as e:
                    record.decoded_invoice_base64 = f"Error decoding Base64: {str(e)}"
            else:
                record.decoded_invoice_base64 = False



    @api.depends('invoice_hexa', 'invoice_base64')
    def _compute_qr_code(self):
        for record in self:
            qr_data = record.invoice_hexa or ''
            if record.invoice_base64:
                try:
                    # Include decoded Base64 content
                    decoded_content = base64.b64decode(record.invoice_base64).decode('utf-8')
                    qr_data += f"\n{decoded_content}"
                except Exception:
                    pass  # Ignore decoding errors

            if qr_data:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                qr_code_data = base64.b64encode(buffer.getvalue())
                record.qr_code = qr_code_data
            else:
                record.qr_code = False


class ResPartner(models.Model):
    _inherit = 'res.partner'

    parent_iqama = fields.Char(string="Parent IQAMA")
    nationality = fields.Char(string="Nationality")
    user_type = fields.Char(
        # [('parent', 'Parent'), ('student', 'Student'), ('teacher', 'Teacher')],
        string="User Type",
    )