import base64
import logging
import os
import subprocess
import tempfile

import koji
from koji.context import context
from koji.plugin import callback

import rpm


log = logging.getLogger("koji.plugin.kojihub_posttag_nbsign")


# TODO: Make that a config file
tosign_tags = ("nb5.0-free-testing", "nb5.0-nonfree-testing", "nb7-free")
signing_server = "10.8.16.170"
signing_user = "nbrpm-sign"


class AlreadySignedError(Exception):
    pass


class SigningError(Exception):
    pass


class Signer(object):
    def __init__(self, build):
        self.build = build
        self.builddir = koji.pathinfo.build(build)

        self.sign_cmd = ["/usr/bin/ssh", "-T",
                         "-q", "-o", "StrictHostKeyChecking=no",
                         "%s@%s" % (signing_user, signing_server)]

    def __get_rpm_path(self, rpm_info):
        rpm_path = os.path.join(self.builddir, koji.pathinfo.rpm(rpm_info))

        if os.path.exists(rpm_path):
            return rpm_path

        raise SigningError("Could not sign %s: File does not exist"
                           % rpm_path)

    def __request_signature(self, rpm_path):
        with open(rpm_path, "r") as in_:
            try:
                proc = subprocess.Popen(self.sign_cmd,
                                        stdin=in_,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                out, err = proc.communicate()

                if proc.returncode != 0:
                    raise SigningError("Could not sign %s: %s"
                                       % (os.path.basename(rpm_path), err))

            except Exception as e:
                raise SigningError("Could not sign %s: %s"
                                   % (os.path.basename(rpm_path), e))

        # So signing seems to have gone well...
        tmpfd, tmppath = tempfile.mkstemp()
        tmpfile = os.fdopen(tmpfd, "w")
        tmpfile.write(out)
        tmpfile.close()

        return tmppath

    def __get_sighdr(self, signed_rpm_path, rpm_path, rpm_info):
        try:
            header_fields = koji.get_header_fields(signed_rpm_path, ('siggpg', 'sigpgp'))

        except rpm.error:
            raise SigningError("Signing server returned corrupt RPM for %s"
                               % rpm_path)

        if header_fields['siggpg'] is not None:
            sigkey = header_fields['siggpg']

        elif header_fields['sigpgp'] is not None:
            sigkey = header_fields['sigpgp']

        else:
            raise SigningError("Signing server returned unsigned RPM for %s"
                               % rpm_path)

        sigkey = koji.get_sigpacket_key_id(sigkey)

        sigs = context.handlers.call("queryRPMSigs",
                                     rpm_id=rpm_info['id'],
                                     sigkey=sigkey)

        if len(sigs) > 0:
            raise AlreadySignedError()

        return koji.rip_rpm_sighdr(signed_rpm_path)

    def sign(self):
        rpms = context.handlers.call("listBuildRPMs", self.build["id"])

        for rpm_info in rpms:
            rpm_path = self.__get_rpm_path(rpm_info)

            signed_rpm_tmppath = self.__request_signature(rpm_path)

            try:
                sighdr = self.__get_sighdr(signed_rpm_tmppath, rpm_path,
                                           rpm_info)
                context.handlers.call("addRPMSig", rpm_info['id'],
                                      base64.encodestring(sighdr))

            except AlreadySignedError as e:
                # That's fine, nothing to do here
                pass

            except koji.GenericError as e:
                raise SigningError("Could not upload the signature to Koji: "
                                   "%s" % e)

            os.unlink(signed_rpm_tmppath)


@callback("postTag")
def nbsign(cbtype, tag, build, user, force=False):
    if tag["name"] not in tosign_tags:
        # Not signing builds for this tag
        return

    Signer(build).sign()
