import subprocess
import logging
import sys
import re
import os
from .RecipeClass import Recipe
import tempfile
import glob


class BB:
    def __init__(self):
        pass

    def process(self, conf, reclist):
        if not conf.skip_bitbake:
            logging.info(f"Checking Bitbake environment ...")
            if not self.check_bitbake():
                return False
            self.process_bitbake_env(conf)
            tfile = self.run_showlayers()
        else:
            tfile = conf.bitbake_layers_file

        if not self.check_files(conf):
            return False

        self.process_licman_file(conf.license_manifest, reclist)
        if not self.process_showlayers(tfile, reclist):
            return False

    def check_bitbake(self):
        cmd = "bitbake"
        ret = self.run_cmd(cmd)
        if ret == b'':
            logging.error("Command 'bitbake' not available - check environment or use --skip_bitbake and "
                          "--license_manifest")
            return False

        cmd = "bitbake-layers"
        ret = self.run_cmd(cmd)
        if ret == b'':
            logging.error("Command 'bitbake-layers' not available - check environment or use --skip_bitbake and "
                          "--bitbake_layers_file")
            return False

        return True

    def run_bitbake_env(self):
        cmd = ["bitbake", "-e"]
        ret, out = self.run_cmd(cmd)
        if not ret:
            logging.error("Cannot run 'bitbake -e'")
            return ''
        return out

    def run_showlayers(self):
        cmd = ["bitbake-layers", "show-recipes"]
        ret, out = self.run_cmd(cmd)
        if not ret:
            logging.error("Cannot run 'bitbake-layers show-recipes'")
            return ''
        lfile_name = tempfile.NamedTemporaryFile(mode="w", delete=False)
        with open(lfile_name, "w") as lfile:
            lfile.write(out)

        return lfile_name

    def process_bitbake_env(self, conf):
        lines = self.run_bitbake_env().split('\n')

        rpm_dir = ''
        ipk_dir = ''
        deb_dir = ''
        for mline in lines:
            if re.search(
                    "^(MANIFEST_FILE|DEPLOY_DIR|MACHINE_ARCH|DL_DIR|DEPLOY_DIR_RPM|"
                    "DEPLOY_DIR_IPK|DEPLOY_DIR_DEB|IMAGE_PKGTYPE)=",
                    mline):

                # if re.search('^TMPDIR=', mline):
                #     tmpdir = mline.split('=')[1]
                val = mline.split('=')[1].strip('\"')
                if re.search('^MANIFEST_FILE=', mline):
                    if not conf.license_manifest:
                        conf.license_manifest = val
                        logging.info(f"Bitbake Env: manifestfile={conf.license_manifest}")
                elif re.search('^DEPLOY_DIR=', mline):
                    if not conf.deploy_dir:
                        conf.deploy_dir = val
                        logging.info(f"Bitbake Env: deploydir={conf.deploy_dir}")
                elif re.search('^MACHINE_ARCH=', mline):
                    if not conf.machine:
                        conf.machine = val
                        logging.info(f"Bitbake Env: machine={conf.machine}")
                elif re.search('^DL_DIR=', mline):
                    if not conf.download_dir:
                        conf.download_dir = val
                        logging.info(f"Bitbake Env: download_dir={conf.download_dir}")
                elif not rpm_dir and re.search('^DEPLOY_DIR_RPM=', mline):
                    rpm_dir = val
                    logging.info(f"Bitbake Env: rpm_dir={rpm_dir}")
                elif not ipk_dir and re.search('^DEPLOY_DIR_IPK=', mline):
                    ipk_dir = val
                    logging.info(f"Bitbake Env: ipk_dir={ipk_dir}")
                elif not deb_dir and re.search('^DEPLOY_DIR_DEB=', mline):
                    deb_dir = val
                    logging.info(f"Bitbake Env: deb_dir={deb_dir}")
                elif re.search('^IMAGE_PKGTYPE=', mline):
                    conf.image_pkgtype = val
                    logging.info(f"Bitbake Env: image_pkgtype={conf.image_pkgtype}")

        if conf.package_dir:
            if conf.image_pkgtype == 'rpm' and rpm_dir:
                conf.package_dir = rpm_dir
            elif conf.image_pkgtype == 'ipk' and ipk_dir:
                conf.package_dir = ipk_dir
            elif conf.image_pkgtype == 'deb' and deb_dir:
                conf.package_dir = deb_dir

        if not conf.deploy_dir:
            temppath = os.path.join(conf.build_dir, 'tmp', 'deploy')
            if os.path.isdir(temppath):
                conf.deploy_dir = temppath
        if not conf.download_dir:
            temppath = os.path.join(conf.build_dir, 'downloads')
            if os.path.isdir(temppath):
                conf.download_dir = temppath
        if not conf.package_dir and conf.deploy_dir:
            temppath = os.path.join(conf.deploy_dir, conf.image_pkgtype)
            if os.path.isdir(temppath):
                conf.pkg_dir = temppath

    @staticmethod
    def run_cmd(command):
        try:
            ret = subprocess.run(command, capture_output=True, text=True, timeout=20)
            if ret.returncode != 0:
                logging.error(f"Run command '{command}' failed with error {ret.returncode} - {ret.stderr}")
                return False, ''
            return True, ret.stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Run command '{command}' failed with error {e}")
            return False, ''

        # proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        # proc_stdout = proc.communicate()[0].strip()
        # return proc_stdout

    @staticmethod
    def process_showlayers(showlayers_file, reclist):
        try:
            with open(showlayers_file, "r") as bfile:
                lines = bfile.readlines()
            rec = ""
            bstart = False
            for rline in lines:
                rline = rline.strip()
                if bstart:
                    if rline.endswith(":"):
                        arr = rline.split(":")
                        rec = arr[0]
                    elif rec:
                        arr = rline.split()
                        if len(arr) > 1:
                            layer = arr[0]
                            ver = arr[1]
                            reclist.add_layer_to_recipe(rec, layer, ver)
                        rec = ""
                elif rline.endswith(": ==="):
                    bstart = True

            logging.info(f"- {reclist.count_recipes_without_layer()} recipes without layer reported from layer file")
        except Exception as e:
            logging.error(f"Cannot process bitbake-layers output file '{showlayers_file} - error {e}")
            return False

        return True

    @staticmethod
    def process_licman_file(lic_manifest_file, reclist):
        recipes_total = 0
        try:
            with open(lic_manifest_file, "r") as lfile:
                lines = lfile.readlines()
                ver = ''
                recipe = ''
                for line in lines:
                    # PACKAGE NAME: name
                    # PACKAGE VERSION: ver
                    # RECIPE NAME: rname
                    # LICENSE: License
                    #
                    line = line.strip()
                    if line.startswith("PACKAGE VERSION:"):
                        ver = line.split(': ')[1]
                    elif line.startswith("RECIPE NAME:"):
                        recipe = line.split(': ')[1]

                    if recipe and ver:
                        recipes_total += 1
                        rec_obj = Recipe(recipe, ver)
                        if not reclist.check_recipe_exists(recipe):
                            reclist.recipes.append(rec_obj)
                        ver = ''
                        recipe = ''

                logging.info(f"- {recipes_total} packages found in licman file ({reclist.count()} recipes)")

        except Exception as e:
            logging.error(f"Cannot read license manifest file '{lic_manifest_file}' - error '{e}'")
            sys.exit(2)

        return

    @staticmethod
    def check_files(conf):
        machine = conf.machine.replace('_', '-')

        if not conf.license_manifest:
            if not conf.target or not conf.machine:
                logging.error("Manifest file not specified and it could not be determined as Target not specified or "
                              "machine not identified from environment")
                return False
            else:
                manpath = os.path.join(conf.deploy_dir, "licenses",
                                       f"{conf.target}-{machine}-*", "license.manifest")
                manifest = ""
                manlist = glob.glob(manpath)
                if len(manlist) > 0:
                    # Get most recent file
                    manifest = manlist[-1]

                if not os.path.isfile(manifest):
                    logging.error(f"Manifest file '{manifest}' could not be located")
                    return False
                else:
                    logging.info(f"Located license.manifest file {manifest}")
                    conf.license_manifest = manifest

        imgdir = os.path.join(conf.deploy_dir, "images", machine)
        cvefile = ""

        if os.path.isdir(imgdir):
            for file in sorted(os.listdir(imgdir)):
                if file == conf.target + "-" + machine + ".cve":
                    cvefile = os.path.join(imgdir, file)
                    break

        if not os.path.isfile(cvefile):
            logging.warning(f"CVE check file {cvefile} could not be located - skipping CVE processing")
        else:
            logging.info(f"Located CVE check output file {cvefile}")
            conf.cve_check_file = cvefile

        return True

    @staticmethod
    def get_pkg_files(conf):
        pattern = f"{conf.package_dir}/**/*.{conf.image_package_type}"
        package_paths_list = glob.glob(pattern, recursive=True)
        package_files_list = []
        for path in package_paths_list:
            package_files_list.append(os.path.basename(path))

        return package_files_list

    @staticmethod
    def get_download_files(conf):
        pattern = f"{conf.download_dir}/*"
        # print(pattern)
        all_download_paths_list = glob.glob(pattern, recursive=True)
        download_files_list = []
        for path in all_download_paths_list:
            if not path.endswith(".done"):
                download_files_list.append(path)

        return download_files_list
