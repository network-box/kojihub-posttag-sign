hubplugindir=/usr/lib/koji-hub-plugins
hubpluginconfdir=/etc/koji-hub/plugins


install:
	mkdir -p $(DESTDIR)$(hubplugindir)
	install -p -m 0644 kojihub_posttag_sign.py $(DESTDIR)$(hubplugindir)
	
	mkdir -p $(DESTDIR)$(hubpluginconfdir)
	install -p -m 0644 posttag-sign.conf $(DESTDIR)$(hubpluginconfdir)
