from odoo import http
from odoo.http import request
import requests
from datetime import datetime


class InvoiceSync(http.Controller):
    @http.route('/sync_invoices', type='http', auth='public', methods=['POST'], csrf=False)
    def sync_invoices(self):
        # API Endpoint
        api_url = "https://my.ais.sch.sa/arrowad_e_invoice/fetch_invoices_with_payments"
        params = {"invoice_no": "INV174856"}
        headers = {
            'token': '1SDryVpl7xJ4tx5d',
        }

        # Fetch API Data
        response = requests.get(api_url, headers=headers, params=params)
        if response.status_code != 200:
            return {"error": f"Failed to fetch data. Status code: {response.status_code}"}

        data = response.json()
        if not data.get("isSuccess"):
            return {"error": data.get("errorMessage", "Unknown error")}

        orders = data.get("orders", [])
        for order in orders:
            invoices = order.get("invoices", {})
            payments = order.get("payments", [])

            # Create or Update Invoice in Odoo
            invoice = self._create_or_update_invoice(invoices, order)

            # Process Payments
            for payment in payments:
                payment_obj = self._create_payment(payment, invoice)
                if payment_obj:
                    # Reconcile payment with the invoice
                    self._reconcile_payment(payment_obj, invoice)

        # return {"success": True, "message": "Invoices and payments synced successfully."}

    def _create_or_update_invoice(self, invoices, order):
        """Create or update an invoice in Odoo."""
        existing_invoice = request.env['account.move'].sudo().search(
            [('ref', '=', invoices.get('invoice_no')), ('move_type', '=', 'out_invoice')], limit=1
        )
        if existing_invoice:
            return existing_invoice

        invoice_vals = {
            'move_type': 'out_invoice',  # Customer Invoice
            'partner_id': self._get_partner_id(invoices.get('name'), invoices),
            'invoice_date': invoices.get('invoice_date'),
            'ref': invoices.get('invoice_no'),
            'name': invoices.get('invoice_no'),
            'invoice_hexa': invoices.get('invoice_hexa'),
            'invoice_base64': invoices.get('invoice_base64'),
            'invoice_line_ids': [(0, 0, {
                'name': invoices.get('fee_name'),
                'quantity': 1,
                'price_unit': invoices.get('invoice_net'),
                'tax_ids': [(6, 0, self._get_tax_ids())],  # Add tax if applicable
            })],
        }
        invoice = request.env['account.move'].sudo().create(invoice_vals)
        invoice.action_post()
        return invoice

    def _create_payment(self, payment, invoice):
        """Create a payment in Odoo."""
        payment_vals = {
            'partner_id': invoice.partner_id.id,
            'amount': payment.get('amount'),
            'date': payment.get('transaction_date'),
            'journal_id': self._get_journal_id(),
            'payment_type': 'inbound',
            'ref': payment.get('receipt_ref'),
        }
        payment_obj = request.env['account.payment'].sudo().create(payment_vals)
        payment_obj.action_post()  # Validate the payment
        return payment_obj

    def _reconcile_payment(self, payment_obj, invoice):
        """Reconcile payment with the invoice."""
        try:
            receivable_lines = payment_obj.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            # Pass IDs to js_assign_outstanding_line
            if receivable_lines:
                invoice.js_assign_outstanding_line(receivable_lines.ids)
        except Exception as e:
            return {"error": f"Failed to reconcile payment: {str(e)}"}

    def _get_partner_id(self, partner_name, order):
        """Fetch or create the partner based on the name."""
        partner_vals = {
            'name': partner_name,
            'parent_iqama': order.get('parent_iqama'),
            'nationality': order.get('nationality'),
            'user_type': order.get('user_type'),
        }

        partner = request.env['res.partner'].sudo().search([('name', '=', partner_name)], limit=1)
        if partner:
            partner.write(partner_vals)
        else:
            partner = request.env['res.partner'].sudo().create(partner_vals)
        return partner.id

    def _get_tax_ids(self):
        """Fetch applicable tax IDs."""
        tax = request.env['account.tax'].sudo().search([('type_tax_use', '=', 'sale')], limit=1)
        return tax.ids

    def _get_journal_id(self):
        """Fetch default journal ID for payments."""
        journal = request.env['account.journal'].sudo().search([('type', '=', 'bank')], limit=1)
        return journal.id