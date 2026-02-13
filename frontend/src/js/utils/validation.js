/**
 * Form Validation Utilities
 */

export class Validator {
    constructor(form, rules = {}, options = {}) {
        this.form = form;
        this.rules = rules;
        this.options = {
            validateOnInput: true,
            validateOnBlur: true,
            focusFirstError: true,
            ...options
        };
        this.errors = {};
        this.isValid = true;
        
        this.init();
    }

    init() {
        // Add event listeners
        if (this.options.validateOnInput) {
            this.form.addEventListener('input', (e) => {
                if (e.target.name) {
                    this.validateField(e.target.name);
                }
            });
        }
        
        if (this.options.validateOnBlur) {
            this.form.addEventListener('blur', (e) => {
                if (e.target.name) {
                    this.validateField(e.target.name);
                }
            }, true);
        }
        
        // Prevent default form submission
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            if (this.validate()) {
                this.form.dispatchEvent(new CustomEvent('validSubmit', {
                    detail: { values: this.getValues() }
                }));
            }
        });
    }

    /**
     * Validate entire form
     */
    validate() {
        this.errors = {};
        this.isValid = true;
        
        for (const fieldName in this.rules) {
            this.validateField(fieldName, false);
        }
        
        // Focus first error
        if (!this.isValid && this.options.focusFirstError) {
            const firstErrorField = Object.keys(this.errors)[0];
            const field = this.form.elements[firstErrorField];
            if (field) field.focus();
        }
        
        return this.isValid;
    }

    /**
     * Validate single field
     */
    validateField(fieldName, updateUI = true) {
        const field = this.form.elements[fieldName];
        if (!field) return true;
        
        const rules = this.rules[fieldName];
        if (!rules) return true;
        
        const value = field.value;
        let error = null;
        
        // Run validation rules
        for (const rule of rules) {
            if (rule.validator(value, field)) {
                continue;
            }
            error = rule.message;
            break;
        }
        
        // Update errors
        if (error) {
            this.errors[fieldName] = error;
            this.isValid = false;
        } else {
            delete this.errors[fieldName];
        }
        
        // Update UI
        if (updateUI) {
            this.updateFieldUI(field, error);
        }
        
        return !error;
    }

    /**
     * Update field UI (Bootstrap styling)
     */
    updateFieldUI(field, error) {
        const feedback = field.parentElement.querySelector('.invalid-feedback') ||
                        this.createFeedback(field.parentElement);
        
        if (error) {
            field.classList.add('is-invalid');
            field.classList.remove('is-valid');
            feedback.textContent = error;
            feedback.style.display = 'block';
        } else {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
            feedback.style.display = 'none';
        }
    }

    createFeedback(container) {
        const feedback = document.createElement('div');
        feedback.className = 'invalid-feedback';
        container.appendChild(feedback);
        return feedback;
    }

    /**
     * Get form values
     */
    getValues() {
        const formData = new FormData(this.form);
        const values = {};
        for (const [key, value] of formData.entries()) {
            values[key] = value;
        }
        return values;
    }

    /**
     * Reset form validation
     */
    reset() {
        this.errors = {};
        this.isValid = true;
        
        for (const field of this.form.elements) {
            if (field.name) {
                field.classList.remove('is-invalid', 'is-valid');
                const feedback = field.parentElement.querySelector('.invalid-feedback');
                if (feedback) feedback.style.display = 'none';
            }
        }
    }

    /**
     * Get errors
     */
    getErrors() {
        return this.errors;
    }
}

/**
 * Built-in validation rules
 */
export const ValidationRules = {
    required: (message = 'This field is required') => ({
        validator: (value) => value && value.trim().length > 0,
        message
    }),
    
    email: (message = 'Please enter a valid email') => ({
        validator: (value) => {
            if (!value) return true; // Use with required() for mandatory
            return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
        },
        message
    }),
    
    minLength: (length, message) => ({
        validator: (value) => {
            if (!value) return true;
            return value.length >= length;
        },
        message: message || `Minimum length is ${length} characters`
    }),
    
    maxLength: (length, message) => ({
        validator: (value) => {
            if (!value) return true;
            return value.length <= length;
        },
        message: message || `Maximum length is ${length} characters`
    }),
    
    pattern: (regex, message = 'Invalid format') => ({
        validator: (value) => {
            if (!value) return true;
            return regex.test(value);
        },
        message
    }),
    
    number: (message = 'Please enter a valid number') => ({
        validator: (value) => {
            if (!value) return true;
            return !isNaN(value);
        },
        message
    }),
    
    min: (min, message) => ({
        validator: (value) => {
            if (!value) return true;
            return parseFloat(value) >= min;
        },
        message: message || `Minimum value is ${min}`
    }),
    
    max: (max, message) => ({
        validator: (value) => {
            if (!value) return true;
            return parseFloat(value) <= max;
        },
        message: message || `Maximum value is ${max}`
    }),
    
    match: (fieldName, message) => ({
        validator: (value, field) => {
            if (!value) return true;
            const form = field.form;
            const matchField = form.elements[fieldName];
            return matchField && value === matchField.value;
        },
        message: message || `Values do not match`
    }),
    
    url: (message = 'Please enter a valid URL') => ({
        validator: (value) => {
            if (!value) return true;
            try {
                new URL(value);
                return true;
            } catch {
                return false;
            }
        },
        message
    }),
    
    ip: (message = 'Please enter a valid IP address') => ({
        validator: (value) => {
            if (!value) return true;
            const parts = value.split('.');
            if (parts.length !== 4) return false;
            return parts.every(part => {
                const num = parseInt(part, 10);
                return num >= 0 && num <= 255 && part === num.toString();
            });
        },
        message
    }),
    
    custom: (validatorFn, message = 'Validation failed') => ({
        validator: validatorFn,
        message
    })
};
