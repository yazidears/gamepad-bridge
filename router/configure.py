#!/usr/bin/env python3
"""Create fresh local pairing credentials; never print the PSK."""
import argparse, os, pathlib, re, secrets, struct, uuid
p=argparse.ArgumentParser()
p.add_argument('--output', required=True, type=pathlib.Path)
p.add_argument('--interface', required=True)
p.add_argument('--ap-mac', required=True)
p.add_argument('--country', required=True)
p.add_argument('--channel', required=True, type=int)
args=p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',args.interface): p.error('invalid interface')
if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',args.ap_mac): p.error('invalid AP MAC')
if not re.fullmatch(r'[A-Z]{2}',args.country): p.error('country must be a two-letter code')
if not 1 <= args.channel <= 196: p.error('invalid channel')
os.umask(0o077)
args.output.mkdir(parents=True, exist_ok=False)
root=str(args.output.resolve())
if any(c.isspace() for c in root): p.error('output path must not contain whitespace')
mac=bytes.fromhex(args.ap_mac.replace(':',''))
if mac[0] & 1 or not mac[0] & 2: p.error('AP MAC must be locally administered and unicast')
ssid=b'WiiU'+mac.hex().encode()
pairssid=b'WiiU'+mac.hex().encode()[:-1]+mac.hex().encode()+b'_STA1'
key=secrets.token_hex(32).encode()
def tlv(t,b): return struct.pack('>HH',t,len(b))+b
credential=b''.join(tlv(t,b) for t,b in [(0x1026,b'\1'),(0x1045,ssid),(0x1003,b'\0\x20'),(0x100f,b'\0\x08'),(0x1027,key),(0x1020,mac)])
(args.output/'credentials.bin').write_bytes(tlv(0x100e,credential))
(args.output/'bridge.token').write_bytes(secrets.token_bytes(32))
conf=f'''interface={args.interface}
driver=nl80211
logger_stdout=-1
logger_stdout_level=2
ctrl_interface={root}/control
bssid={args.ap_mac}
hw_mode=a
country_code={args.country}
channel={args.channel}
beacon_int=100
dtim_period=3
macaddr_acl=0
auth_algs=3
wmm_enabled=1
uapsd_advertisement_enabled=1
wmm_ac_be_acm=0
wmm_ac_be_aifs=2
wmm_ac_be_cwmin=4
wmm_ac_be_cwmax=5
wmm_ac_be_txop_limit=47
wmm_ac_bk_acm=0
wmm_ac_bk_aifs=7
wmm_ac_bk_cwmin=4
wmm_ac_bk_cwmax=10
wmm_ac_bk_txop_limit=0
wmm_ac_vi_acm=0
wmm_ac_vi_aifs=3
wmm_ac_vi_cwmin=4
wmm_ac_vi_cwmax=5
wmm_ac_vi_txop_limit=94
wmm_ac_vo_acm=0
wmm_ac_vo_aifs=3
wmm_ac_vo_cwmin=4
wmm_ac_vo_cwmax=5
wmm_ac_vo_txop_limit=47
ieee80211n=1
ssid={pairssid.decode()}
ieee8021x=1
eapol_version=1
eap_server=1
wps_state=2
skip_cred_build=1
extra_cred={root}/credentials.bin
wps_cred_processing=1
uuid={uuid.uuid4()}
manufacturer=Broadcom
model_name=SoftAP
model_number=0
serial_number=0
device_type=6-a4c0e1f4-1
device_name={ssid.decode()}
os_version=80000000
config_methods=label push_button
vendor_elements=dd0800904c0700513206dd09001018020100040000
'''
(args.output/'pairing.conf').write_text(conf)
runtime=conf[:conf.index('\nssid=')]+f"\nssid={ssid.decode()}\nwpa=2\nwpa_key_mgmt=WPA-PSK\nrsn_pairwise=CCMP\nwpa_psk={key.decode()}\n" + "vendor_elements=dd0800904c0700513206dd09001018020100040000\n"
(args.output/'runtime.conf').write_text(runtime)
print('Created private pairing.conf, runtime.conf, credentials.bin and bridge.token')

digits=[(mac[-1] >> shift) & 3 for shift in (6,4,2,0)]
symbols=('spade','heart','diamond','club')
print('Enter these GamePad symbols: ' + ' '.join(symbols[d] for d in digits))
print('WPS PIN: ' + ''.join(str(d) for d in digits) + '5678')
