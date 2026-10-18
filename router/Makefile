CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra
CPPFLAGS += -I.
PREFIX ?= /usr/local

.PHONY: all check clean install
all: frame-proxy
frame-proxy: frame-proxy.c media.h clock-filter.h clock-anchor.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ frame-proxy.c
check:
	mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) -o build/test-media tests/test-media.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -o build/test-clock-anchor tests/test-clock-anchor.c
	./build/test-media
	./build/test-clock-anchor
install: frame-proxy
	install -d $(DESTDIR)$(PREFIX)/sbin
	install -m 755 frame-proxy $(DESTDIR)$(PREFIX)/sbin/gamepad-frame-proxy
clean:
	rm -rf build frame-proxy
