import os
from flask import Flask, jsonify

app = Flask(__name__)

# The JSON response data you provided
MOCK_CHECKOUT_RESPONSE = {
    "isProMember": False,
    "savings_delight_widget": {
        "savingsIconMedia": {
            "url": "https://cdn.magicpin.com/assets/lottie/savings_lottie.json",
            "type": "lottie",
            "repeatCount": 4,
            "autoPlay": True
        },
        "suffixText": {
            "lineHeight": 0,
            "value": "on this purchase!",
            "size": 0
        },
        "savings": 10,
        "style": {
            "background": {
                "bgColors": ["purple_light"],
                "cornersRadii": [12],
                "strokeWidth": 0.5,
                "strokeColor": "tags_tonal_palette_purple"
            },
            "margin": {
                "top": 8,
                "end": 16,
                "start": 16,
                "bottom": 0
            }
        },
        "text": {
            "lineHeight": 20,
            "value": "₹{savings}",
            "fontType": "font_semi_bold",
            "size": 14
        },
        "type": "savings-delight-widget",
        "confettiLottie": {
            "url": "https://cdn.magicpin.com/assets/lottie/savings_delight_lottie.json",
            "repeatCount": 1,
            "autoPlay": True
        },
        "prefixText": {
            "lineHeight": 0,
            "value": "Saving",
            "size": 0
        }
    },
    "magicCash": {
        "available": True,
        "amount": 0,
        "balance": 2,
        "eligible": True,
        "usableAmount": 2
    },
    "maxSavings": 10,
    "voucherWorthPrice": 500,
    "payCtaAmount": 491,
    "message": None,
    "voucherMagicpinAmount": 10,
    "subTotalAmount": None,
    "enablePay": True,
    "paymentDetailsWidget": {
        "txnData": [
            {
                "style": {
                    "background": {
                        "corners_radii": [20],
                        "bg_colors": ["#FFFFFF"]
                    },
                    "margin": {
                        "top": 8,
                        "bottom": 8,
                        "start": 0,
                        "end": 0
                    }
                },
                "details": [
                    {
                        "type": "row-data",
                        "detail": {"value": "₹0", "color": "#333333", "font_type": "font_semi_bold"},
                        "label": {"value": "Bill amount", "color": "#333333", "font_type": "font_medium"}
                    },
                    {
                        "type": "row-data",
                        "detail": {
                            "value": "-10",
                            "icons": [None, None, {"icon_type": "MAGIC_COIN_16"}, None],
                            "color": "#4DA940",
                            "font_type": "font_semi_bold"
                        },
                        "label": {
                            "value": "Save using magicPoints",
                            "spans": [
                                {
                                    "type": "typeface-span",
                                    "span_info": {"end_index": -1, "span_text": "Save", "start_index": -1},
                                    "font_type": "font_semi_bold",
                                    "color": "#6561E8"
                                }
                            ],
                            "icons": [None, None, {"icon_type": "MAGIC_COIN_16"}, None],
                            "color": "#333333",
                            "font_type": "font_medium"
                        }
                    },
                    {
                        "type": "row-data",
                        "detail": {
                            "value": "₹1 ₹0.8",
                            "spans": [
                                {"type": "text-decoration-span", "span_info": {"span_text": "₹1"}, "strike_through": True},
                                {"type": "typeface-span", "span_info": {"span_text": "₹1"}, "color": "#767676"}
                            ],
                            "color": "#333333",
                            "font_type": "font_semi_bold"
                        },
                        "label": {"value": "Platform Fee", "color": "#333333", "font_type": "font_medium"}
                    },
                    {
                        "type": "row-data",
                        "detail": {"value": "₹0.1", "color": "#333333", "font_type": "font_semi_bold"},
                        "label": {"value": "Taxes and Charges", "color": "#333333", "font_type": "font_medium"}
                    },
                    {"type": "divider"},
                    {
                        "type": "row-data",
                        "detail": {"value": "₹491", "color": "#333333"},
                        "label": {"value": "To Pay", "color": "#333333", "font_type": "font_semi_bold"}
                    }
                ]
            }
        ],
        "heading": {"value": "Payment Details"},
        "spans": None,
        "style": {
            "background": {
                "corners_radii": [24, 24, 0, 0],
                "bg_colors": ["#F6F6FB"]
            },
            "padding": {"top": 24, "bottom": 24}
        },
        "type": "payment-details-widget",
        "title": {
            "style": {
                "background": {
                    "corners_radii": [10],
                    "stroke_width": 0.5,
                    "stroke_color": "#E8E8E8",
                    "bg_colors": ["#FFFFFF"]
                }
            },
            "value": "You have: 278",
            "icons": [None, None, {"icon_type": "MAGIC_COIN_16"}, None],
            "spans": [
                {
                    "type": "typeface-span",
                    "span_info": {"end_index": -1, "span_text": "278", "start_index": -1},
                    "font_type": "font_semi_bold"
                }
            ]
        }
    },
    "magicpin_balance": 278,
    "savings_highlight_widget": {"lineHeight": 0, "value": "Save ₹10", "size": 0},
    "isWalletOnly": False,
    "magicProAutoAdded": False,
    "remainingPayAmount": 491,
    "voucherInfoList": [
        {
            "worthPriceForSavings": 500,
            "currency": "₹",
            "tnc_details": {
                "multiple_vouchers_allowed": {"displayText": "<b>Multiple Vouchers</b> are applicable on the same bill", "data_type": "Boolean", "dataType": "Boolean", "icon": "multiple_voucher.png", "value": True, "name": "multiple_vouchers_allowed", "display_text": "<b>Multiple Vouchers</b> are applicable on the same bill"},
                "refundable": {"displayText": "a. <b>Non Refundable.</b>", "data_type": "Boolean", "dataType": "Boolean", "icon": "not_refundable.png", "value": False, "name": "refundable", "display_text": "a. <b>Non Refundable.</b>"}
            },
            "redemptionSteps": [{"steps": [{"sub_title": "", "title": "Go to Blinkit App.  "}, {"sub_title": "", "title": "Add items to Cart.  "}, {"sub_title": "", "title": "Select Blinkit Money as Payment Method.  "}, {"sub_title": "", "title": "Click on Claim Gift Card .  "}, {"sub_title": "", "title": "Enter the 16 digit card number and 6 digit pin and tap on claim."}]}],
            "paymentSystemAmount": 490,
            "voucherWorthPrice": 500,
            "redemptionCount": 1,
            "isGroupbuyActive": False,
            "tnc_validity": {
                "valid_days": {"displayText": None, "data_type": "String", "dataType": "String", "icon": "valid_all_days.png", "value": "1111111", "name": "valid_days", "display_text": None},
                "expiry": {"displayText": "<b>Expires in 60 days </b> from date of purchase.", "data_type": "Integer", "dataType": "Integer", "icon": "expiry.png", "value": 60, "name": "expiry", "display_text": "<b>Expires in 60 days </b> from date of purchase."}
            },
            "singleVoucherMaxUsableBalance": 10,
            "crossSellVoucher": False,
            "gmv": 500,
            "magicpinAmount": 0,
            "walletUsablePercentage": 2,
            "ctcDiscountDto": {"pgAmt": 0, "magicPoints": 0, "totalDiscount": 0},
            "voucherAmount": 500,
            "redemptionType": "VOUCHER",
            "magicpinBalance": 278,
            "merchantDto": {"userId": 4376387, "merchantName": "Blinkit"},
            "howToRedeem": "a. <b>How to redeem the voucher</b>. b. Go to Blinkit App. b. Add items to Cart. b. Select Blinkit Money as Payment Method. b. Click on Claim Gift Card . b. Enter the 16 digit card number and 6 digit pin and tap on claim.",
            "merchantName": "Grofers : PAN India",
            "info": "Gift Voucher worth Rs. 500",
            "tncDetails": [
                {"displayText": "a. <b>Non Refundable.</b>", "data_type": "Boolean", "dataType": "Boolean", "icon": "not_refundable.png", "value": False, "name": "refundable", "display_text": "a. <b>Non Refundable.</b>"},
                {"displayText": "<b>Multiple Vouchers</b> are applicable on the same bill", "data_type": "Boolean", "dataType": "Boolean", "icon": "multiple_voucher.png", "value": True, "name": "multiple_vouchers_allowed", "display_text": "<b>Multiple Vouchers</b> are applicable on the same bill"}
            ],
            "earnCashback": 0,
            "isStockAvailable": True,
            "magicCashCashBack": 0,
            "voucherType": "cash",
            "maxRedemptionsPerTx": 10,
            "merchant_name": "Grofers : PAN India",
            "tncValidity": [
                {"displayText": None, "data_type": "String", "dataType": "String", "icon": "valid_all_days.png", "value": "1111111", "name": "valid_days", "display_text": None},
                {"displayText": "<b>Expires in 60 days </b> from date of purchase.", "data_type": "Integer", "dataType": "Integer", "icon": "expiry.png", "value": 60, "name": "expiry", "display_text": "<b>Expires in 60 days </b> from date of purchase."}
            ],
            "tncString": "a. <b>Details</b>. b. This is a Blinkit Gift Voucher/Gift Card and is accepted on the Blinkit mobile application (Android and iOS). b. The person having the GV/GC is deemed to be the beneficiary. b. This is a one-time use GV/GC. Once the GV/GC is added to the Blinkit Wallet, you can partially redeem the balance as per your convenience. b. GV/GC redemptions are limited to ?25,000 per user, per calendar month. b. The GV/GC can be clubbed with the existing offers. b. The GV/GC can be redeemed only towards the purchase of eligible products on the Blinkit Platform. It cannot be used to buy other Gift Cards or Vouchers. b. Multiple GV/GC can be used against one bill. b. The GV/GC balance is added to the user?s Blinkit Account (Blinkit Money) in case of cancellations. b. Blinkit reserves the right to deny or block a GV/GC if it suspects duplicity, fraud, or unlawful use. b. Blinkit reserves the right to void the GV/GC, close the user?s account, and recover payment from alternative sources the Gift Card is fraudulently or unlawfully obtained or The beneficiary/KYC details as per RBI guidelines are found to be incorrect or insufficient. Credit and debit cards issued outside India cannot be used to purchase a Blinkit GV/GC. The GV/GC is not a legal tender or replacement for a debit/credit card. The offer is valid for all the products available on the Blinkit Mobile App. GV/GCs are non-refundable, may not be exchanged, transferred, or resold, and may not be redeemed for cash. Neither Blinkit nor Pinelabs makes any express or implied warranties regarding the GV/GC, including but not limited to warranties of merchantability or fitness for a particular purpose. b. Blinkit/GyFTR and magicpin reserves the right to change, cancel, or update any of the terms and conditions of this offer at any time without prior notice. b. Blinkit reserves the right to modify these terms and conditions at any time, without prior notice. Continued use of the GV/GC constitutes acceptance of the updated terms. b. Blinkit may choose not to honor the offer if there is any suspicion of misuse or abuse of the offer, and we are not required to explain such cases. b. Blinkit/GyFTR and magicpin is not responsible for lost, damaged, or stolen GV/GCs. b. The courts at New Delhi shall have exclusive jurisdiction for any disputes arising in relation to Gift Voucher. b. For any questions or issues related to Gift Voucer, raise a request at www.gvhelpdesk.com or write to info@blinkit.com.",
            "groupbuyActive": False,
            "roaId": 3099481,
            "menuPrice": 500,
            "productType": "VOUCHER"
        }
    ],
    "magicProCheckoutItem": None,
    "wallet_usable_percentage": 2,
    "magicpayMagicpinAmountWithoutDiscount": None,
    "magicpay_savings_widget": {
        "style": {
            "background": {
                "corners_radii": [24],
                "bg_colors": ["#ffffff"]
            }
        },
        "text": {
            "value": "₹{savings}"
        },
        "savings": 10,
        "prefix_text": {
            "value": "Saving"
        },
        "suffix_text": {
            "value": "🎉"
        }
    },
    "tapToPayApplicable": None,
    "payButtonDisable": False,
    "magicProSubscriptionId": None,
    "limitExhaustText": None,
    "currency": "₹",
    "subscriptionUsableAmount": None,
    "purchaseConfirmationMessage": None,
    "merchantName": "Blinkit",
    "pg_amount": 491,
    "magicpay_percent": None,
    "checkoutConfirmationMessage": None,
    "magicpin_amount": 10,
    "lazyPayTnc": None,
    "ondcMetroTicketRequest": None,
    "magicpayMagicpinAmount": None,
    "totalSavings": 9,
    "status": 200,
    "lastUsedPaymentOptions": None,
    "maxUsableBalance": 10,
    "orderSummaryFooterText": None,
    "magicProAmount": None,
    "enablePayLater": False,
    "merchantUserId": "4376387",
    "userCouponInfo": None,
    "multipleRedemptions": None,
    "payment_offers": None,
    "earnCashback": 0,
    "checkoutConsentConfirmation": None,
    "orderSummaryFooterWidget": {
        "titleText": None,
        "action": "",
        "backgroundColor": "#FFF7F5",
        "subTitle": "",
        "titleColor": "#EC3C3C"
    },
    "checkLocationPermission": True,
    "voucherMagicpinAmountWithoutDiscount": None
}

@app.route('/api/checkout', methods=['GET', 'POST'])
def checkout_api():
    """
    API Endpoint that returns the mock checkout response.
    """
    return jsonify(MOCK_CHECKOUT_RESPONSE)

if __name__ == '__main__':
    # Get the port from the environment variable (required for hosting platforms)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
