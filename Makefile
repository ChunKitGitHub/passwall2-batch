include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-passwall2-batch
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

PKG_MAINTAINER:=Your Name <your@email.com>
PKG_LICENSE:=MIT

LUCI_TITLE:=LuCI support for Passwall2 Batch Import
LUCI_DESCRIPTION:=Batch import HTTP/SOCKS nodes for Passwall2 with shunt rules
LUCI_DEPENDS:=+luci-base +passwall2
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

define Package/$(PKG_NAME)/conffiles
endef

# call BuildPackage - OpenWrt buildance for creating ipk
$(eval $(call BuildPackage,$(PKG_NAME)))
