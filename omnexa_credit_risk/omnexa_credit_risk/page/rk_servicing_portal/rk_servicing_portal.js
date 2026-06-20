frappe.pages["rk-servicing-portal"].on_page_load = function (wrapper) {
	function boot() {
		if (window.omnexa_finance && omnexa_finance.bootPortalPage) {
			omnexa_finance.bootPortalPage(wrapper, "rk-servicing-portal");
			return;
		}
		frappe.require("/assets/omnexa_core/js/finance_portal_page_boot.js", function () {
			omnexa_finance.bootPortalPage(wrapper, "rk-servicing-portal");
		});
	}
	boot();
};
