from datetime import date
from calendar import monthrange
import re

from django import forms
from django.db.models import get_model
from django.utils.translation import ugettext_lazy as _

from oscar.apps.address.forms import AbstractAddressForm
from . import bankcards

Country = get_model('address', 'Country')
BillingAddress = get_model('order', 'BillingAddress')
Bankcard = get_model('payment', 'Bankcard')


class BankcardNumberField(forms.CharField):

    def __init__(self, *args, **kwargs):
        _kwargs = {
            'max_length': 20,
            'widget': forms.TextInput(attrs={'autocomplete': 'off'}),
            'label': _("Card number")
        }
        _kwargs.update(kwargs)
        super(BankcardNumberField, self).__init__(*args, **_kwargs)

    def clean(self, value):
        """
        Check if given CC number is valid and one of the
        card types we accept
        """
        non_decimal = re.compile(r'\D+')
        value = non_decimal.sub('', value.strip())

        if value and not bankcards.luhn(value):
            raise forms.ValidationError(
                _("Please enter a valid credit card number."))
        return super(BankcardNumberField, self).clean(value)


class BankcardMonthWidget(forms.MultiWidget):
    """
    Widget containing two select boxes for selecting the month and year
    """
    def decompress(self, value):
        return [value.month, value.year] if value else [None, None]

    def format_output(self, rendered_widgets):
        html = u' '.join(rendered_widgets)
        return u'<span style="white-space: nowrap">%s</span>' % html


class BankcardMonthField(forms.MultiValueField):
    """
    A modified version of the snippet: http://djangosnippets.org/snippets/907/
    """
    default_error_messages = {
        'invalid_month': _('Enter a valid month.'),
        'invalid_year': _('Enter a valid year.'),
    }
    num_years = 5

    def __init__(self, *args, **kwargs):
        # Allow the number of years to be specified
        if 'num_years' in kwargs:
            self.num_years = kwargs.pop('num_years')

        errors = self.default_error_messages.copy()
        if 'error_messages' in kwargs:
            errors.update(kwargs['error_messages'])

        fields = (
            forms.ChoiceField(
                choices=self.month_choices(),
                error_messages={'invalid': errors['invalid_month']}),
            forms.ChoiceField(
                choices=self.year_choices(),
                error_messages={'invalid': errors['invalid_year']}),
        )
        if 'widget' not in kwargs:
            kwargs['widget'] = BankcardMonthWidget(
                widgets=[fields[0].widget, fields[1].widget])
        super(BankcardMonthField, self).__init__(fields, *args, **kwargs)

    def month_choices(self):
        return []

    def year_choices(self):
        return []


class BankcardExpiryMonthField(BankcardMonthField):
    num_years = 10

    def __init__(self, *args, **kwargs):
        today = date.today()
        _kwargs = {
            'required': True,
            'label': _("Valid to"),
            'initial': ["%.2d" % today.month, today.year]
        }
        _kwargs.update(kwargs)
        super(BankcardExpiryMonthField, self).__init__(*args, **_kwargs)

    def month_choices(self):
        return [("%.2d" % x, "%.2d" % x) for x in xrange(1, 13)]

    def year_choices(self):
        return [(x, x) for x in xrange(date.today().year,
                                       date.today().year + self.num_years)]

    def clean(self, value):
        expiry_date = super(BankcardExpiryMonthField, self).clean(value)
        if date.today() > expiry_date:
            raise forms.ValidationError(
                _("The expiration date you entered is in the past."))
        return expiry_date

    def compress(self, data_list):
        if data_list:
            if data_list[1] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_year']
                raise forms.ValidationError(error)
            if data_list[0] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_month']
                raise forms.ValidationError(error)
            year = int(data_list[1])
            month = int(data_list[0])
            # find last day of the month
            day = monthrange(year, month)[1]
            return date(year, month, day)
        return None


class BankcardStartingMonthField(BankcardMonthField):

    def __init__(self, *args, **kwargs):
        _kwargs = {
            'required': False,
            'label': _("Valid from"),
        }
        _kwargs.update(kwargs)
        super(BankcardStartingMonthField, self).__init__(*args, **_kwargs)

    def month_choices(self):
        months = [("%.2d" % x, "%.2d" % x) for x in xrange(1, 13)]
        months.insert(0, ("", "--"))
        return months

    def year_choices(self):
        today = date.today()
        years = [(x, x) for x in xrange(today.year - self.num_years,
                                        today.year + 1)]
        years.insert(0, ("", "--"))
        return years

    def clean(self, value):
        starting_date = super(BankcardMonthField, self).clean(value)
        if starting_date and date.today() < starting_date:
            raise forms.ValidationError(
                _("The starting date you entered is in the future."))
        return starting_date

    def compress(self, data_list):
        if data_list:
            if data_list[1] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_year']
                raise forms.ValidationError(error)
            if data_list[0] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_month']
                raise forms.ValidationError(error)
            year = int(data_list[1])
            month = int(data_list[0])
            return date(year, month, 1)
        return None


class BankcardCCVField(forms.RegexField):

    def __init__(self, *args, **kwargs):
        _kwargs = {
            'required': True,
            'label': _("CCV number"),
            'widget': forms.TextInput(attrs={'size': '5'}),
            'error_message': _("Please enter a 3 or 4 digit number"),
            'help_text': _("This is the 3 or 4 digit security number "
                           "on the back of your bankcard")
        }
        _kwargs.update(kwargs)
        super(BankcardCCVField, self).__init__(
            r'^\d{3,4}$', *args, **_kwargs)

    def clean(self, value):
        if value is not None:
            value = value.strip()
        return super(BankcardCCVField, self).clean(value)


class BankcardForm(forms.ModelForm):
    number = BankcardNumberField()
    ccv = BankcardCCVField()
    start_month = BankcardStartingMonthField()
    expiry_month = BankcardExpiryMonthField()

    class Meta:
        model = Bankcard
        fields = ('number', 'start_month', 'expiry_month', 'ccv')

    def save(self, *args, **kwargs):
        # It doesn't really make sense to save directly from the form as saving
        # will obfuscate some of the card details which you normally need to
        # pass to a payment gateway.  Better to use the bankcard property below
        # to get the cleaned up data, then once you've used the sensitive
        # details, you can save.
        raise RuntimeError("Don't save bankcards directly from form")

    @property
    def bankcard(self):
        """
        Return an instance of the Bankcard model (unsaved)
        """
        return Bankcard(number=self.cleaned_data['number'],
                        expiry_date=self.cleaned_data['expiry_month'],
                        start_date=self.cleaned_data['start_month'],
                        ccv=self.cleaned_data['ccv'])


class BillingAddressForm(AbstractAddressForm):

    def __init__(self, *args, **kwargs):
        super(BillingAddressForm, self).__init__(*args, **kwargs)
        self.set_country_queryset()

    def set_country_queryset(self):
        self.fields['country'].queryset = Country._default_manager.all()

    class Meta:
        model = BillingAddress
        exclude = ('search_text',)
