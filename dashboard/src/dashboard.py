"""The main module of the QA Dashboard."""
import json
import datetime
import os
import sys
import requests
import csv
import shutil

from fastlog import log

from coreapi import CoreApi
from jobsapi import JobsApi
from configuration import Configuration
from results import Results
from html_generator import generate_dashboard
from perf_tests import PerfTests
from smoke_tests import SmokeTests
from sla import SLA
from ci_jobs import CIJobs
from cliargs import cli_parser
from config import Config
from repositories import Repositories
from progress_bar import progress_bar_class, progress_bar_width
from source_files import get_source_files
from unit_tests import unit_test_coverage_ok, read_unit_test_coverage
from charts import generate_charts
from git_utils import clone_or_fetch_repository


def check_environment_variable(env_var_name):
    """Check if the given environment variable exists."""
    log.info("Checking: {e} environment variable existence".format(
        e=env_var_name))
    if env_var_name not in os.environ:
        log.failure("Fatal: {e} environment variable has to be specified"
                    .format(e=env_var_name))
        sys.exit(1)
    else:
        log.success("ok")


def check_environment_variables():
    """Check if all required environment variables exist."""
    environment_variables = [
        "F8A_API_URL_STAGE",
        "F8A_API_URL_PROD",
        "F8A_JOB_API_URL_STAGE",
        "F8A_JOB_API_URL_PROD",
        "RECOMMENDER_API_TOKEN_STAGE",
        "RECOMMENDER_API_TOKEN_PROD",
        "JOB_API_TOKEN_STAGE",
        "JOB_API_TOKEN_PROD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_REGION_NAME"]
    for environment_variable in environment_variables:
        check_environment_variable(environment_variable)


def check_system(core_api, jobs_api):
    """Check if all system endpoints are available and that tokens are valid."""
    # try to access system endpoints
    print("Checking: core API and JOBS API endpoints")
    core_api_available = core_api.is_api_running()
    jobs_api_available = jobs_api.is_api_running()

    if core_api_available and jobs_api_available:
        print("    ok")
    else:
        print("    Fatal: tested system is not available")

    # check the authorization token for the core API
    print("Checking: authorization token for the core API")
    core_api_auth_token = core_api.check_auth_token_validity()

    if core_api_auth_token:
        print("    ok")
    else:
        print("    error")

    # check the authorization token for the jobs API
    print("Checking: authorization token for the jobs API")
    jobs_api_auth_token = jobs_api.check_auth_token_validity()

    if jobs_api_auth_token:
        print("    ok")
    else:
        print("    error")

    return {"core_api_available": core_api_available,
            "jobs_api_available": jobs_api_available,
            "core_api_auth_token": core_api_auth_token,
            "jobs_api_auth_token": jobs_api_auth_token}


# files that are to be ignored by Pylint
ignored_files_for_pylint = {
}

# files that are to be ignored by Pydocchecker
ignored_files_for_pydocstyle = {
    "fabric8-analytics-worker": ["tests/data/license/license.py"]
}

ci_job_types = [
    "test_job",
    "build_job",
    "pylint_job",
    "pydoc_job"
]

teams = [
    "core",
    "integration"
]

JENKINS_URL = "https://ci.centos.org"
JOBS_STATUSES_FILENAME = "jobs.json"


def run_pylint(repository):
    """Run Pylint checker against the selected repository."""
    with log.indent():
        log.info("Running Pylint for the repository " + repository)
        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "./run-linter.sh > ../../{repo}.linter.txt;" +
                   "popd >> /dev/null").format(repo=repository)
        os.system(command)
        log.success("Done")


def run_docstyle_check(repository):
    """Run PyDocsStyle checker against the selected repository."""
    with log.indent():
        log.info("Running DocStyle checker for the repository " + repository)
        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "./check-docstyle.sh > ../../{repo}.pydocstyle.txt;" +
                   "popd >> /dev/null").format(
            repo=repository)
        os.system(command)
        log.success("Done")


def run_cyclomatic_complexity_tool(repository):
    """Run Cyclomatic Complexity tool against the selected repository."""
    with log.indent():
        log.info("Running cyclomatic complexity checker for the repository " + repository)
        for i in range(ord('A'), 1 + ord('F')):
            rank = chr(i)
            command = ("pushd repositories/{repo} >> /dev/null;" +
                       "radon cc -a -s -n {rank} -i venv . |ansi2html.py > " +
                       "../../{repo}.cc.{rank}.html;" +
                       "popd >> /dev/null").format(repo=repository, rank=rank)
            os.system(command)

        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "radon cc -s -j -i venv . > ../../{repo}.cc.json;" +
                   "popd >> /dev/null").format(repo=repository)
        os.system(command)
        log.success("Done")


def run_maintainability_index(repository):
    """Run Maintainability Index tool against the selected repository."""
    with log.indent():
        log.info("Running maintainability index checker for the repository " + repository)
        for i in range(ord('A'), 1 + ord('C')):
            rank = chr(i)
            command = ("pushd repositories/{repo} >> /dev/null;" +
                       "radon mi -s -n {rank} -i venv . | ansi2html.py " +
                       "> ../../{repo}.mi.{rank}.html;" +
                       "popd >> /dev/null").format(repo=repository, rank=rank)
            os.system(command)

        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "radon mi -s -j -i venv . > ../../{repo}.mi.json;popd >> /dev/null"). \
            format(repo=repository)
        os.system(command)
        log.success("Done")


def run_dead_code_detector(repository):
    """Run dead code detector tool against the selected repository."""
    with log.indent():
        log.info("Running dead code detector for the repository " + repository)
        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "./detect-dead-code.sh > ../../{repo}.dead_code.txt;" +
                   "popd >> /dev/null").format(repo=repository)
        os.system(command)
        log.success("Done")


def run_common_errors_detector(repository):
    """Run common issues detector tool against the selected repository."""
    with log.indent():
        log.info("Running common issues detector for the repository " + repository)
        command = ("pushd repositories/{repo} >> /dev/null;" +
                   "./detect-common-errors.sh > ../../{repo}.common_errors.txt;" +
                   "popd >> /dev/null").format(repo=repository)
        os.system(command)
        log.success("Done")


def percentage(part1, part2):
    """Compute percentage of failed tests."""
    total = part1 + part2
    if total == 0:
        return "0"
    perc = 100.0 * part2 / total
    return "{:.0f}".format(perc)


def parse_linter_results(filename):
    """Parse results generated by Python linter or by PyDocStyle."""
    source = None

    files = {}
    passed = 0
    failed = 0
    total = 0

    with open(filename) as fin:
        for line in fin:
            line = line.rstrip()
            if line.endswith(".py"):
                source = line.strip()
            if line.endswith("    Pass"):
                if source:
                    passed += 1
                    total += 1
                    files[source] = True
            if line.endswith("    Fail"):
                if source:
                    failed += 1
                    total += 1
                    files[source] = False

    display_results = bool(files)

    return {"display_results": display_results,
            "files": files,
            "total": total,
            "passed": passed,
            "failed": failed,
            "passed%": percentage(failed, passed),
            "failed%": percentage(passed, failed),
            "progress_bar_class": progress_bar_class(percentage(failed, passed)),
            "progress_bar_width": progress_bar_width(percentage(failed, passed))}


def parse_pylint_results(repository):
    """Parse results generated by Python linter."""
    return parse_linter_results(repository + ".linter.txt")


def parse_docstyle_results(repository):
    """Parse results generated by PyDocStyle."""
    return parse_linter_results(repository + ".pydocstyle.txt")


def prepare_radon_results():
    """Prepare result structure for storing ranks measured by the 'radon' tool."""
    return {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}


def parse_cyclomatic_complexity(repository):
    """Parse results generated by 'radon cc'."""
    results = prepare_radon_results()
    with open(repository + ".cc.json") as fin:
        data = json.load(fin)
        for module, blocks in data.items():
            for block in blocks:
                rank = block["rank"]
                results[rank] += 1

    results["status"] = results["D"] == 0 and \
        results["E"] == 0 and results["F"] == 0
    return results


def parse_maintainability_index(repository):
    """Parse results generated by 'radon mi'."""
    results = prepare_radon_results()
    with open(repository + ".mi.json") as fin:
        data = json.load(fin)
        for module, mi in data.items():
            rank = mi["rank"]
            results[rank] += 1

    results["status"] = results["B"] == 0 and results["C"] == 0
    return results


def parse_dead_code(repository):
    """Parse results generated by 'vulture' tool."""
    return parse_linter_results(repository + ".dead_code.txt")


def parse_common_errors(repository):
    """Parse results generated by 'Pyflakes' tool."""
    return parse_linter_results(repository + ".common_errors.txt")


def compute_status(source_files, linter_checks_total, ignored_pylint_files, docstyle_checks_total,
                   ignored_pydocstyle_files, linter_checks, docstyle_checks, unit_test_coverage,
                   cyclomatic_complexity, maintainability_index, code_coverage_threshold,
                   dead_code, common_errors):
    """Compute the overall status from various metrics."""
    return source_files == (linter_checks_total + ignored_pylint_files) and \
        source_files == (docstyle_checks_total + ignored_pydocstyle_files) and \
        linter_checks["failed"] == 0 and docstyle_checks["failed"] == 0 and \
        unit_test_coverage_ok(unit_test_coverage, code_coverage_threshold) and \
        cyclomatic_complexity["status"] and \
        maintainability_index["status"] and \
        dead_code["failed"] == 0 and common_errors["failed"] == 0


def remark_linter(source_files, linter_checks_total, ignored_pylint_files, display_results):
    """Generate remark when not all source files are checked by linter."""
    if not display_results:
        return "<li>linter is not setup</li>"
    elif source_files != linter_checks_total + ignored_pylint_files:
        return "<li>not all source files are checked by linter</li>"
    return ""


def remark_docstyle(source_files, docstyle_checks_total, ignored_pydocstyle_files, display_results):
    """Generate remark when not all source files are checked by pydocstyle."""
    if not display_results:
        return "<li>docstyle checker is not setup</li>"
    elif source_files != docstyle_checks_total + ignored_pydocstyle_files:
        return "<li>not all source files are checked by pydocstyle</li>"
    return ""


def remark_linter_vs_docstyle(linter_checks_total, ignored_pylint_files,
                              docstyle_checks_total, ignored_pydocstyle_files):
    """Generate remark when linter checked different files that pydocstyle checker."""
    if linter_checks_total + ignored_pylint_files != \
       docstyle_checks_total + ignored_pydocstyle_files:
        return ", linter checked {n1} files, but pydocstyle checked {n2} files".format(
            n1=linter_checks_total, n2=docstyle_checks_total)
    return ""


def remark_unit_test_coverage(unit_test_coverage, code_coverage_threshold):
    """Generate remark for unit test coverage problems."""
    if unit_test_coverage is not None:
        if not unit_test_coverage_ok(unit_test_coverage, code_coverage_threshold):
            return "<li>improve code coverage</li>"
        else:
            return ""
    else:
        return "<li>unit tests has not been setup</li>"


def dead_code_remark(dead_code):
    """Generate remark for dead code detection."""
    if dead_code["display_results"]:
        if dead_code["failed"] != 0:
            return "<li>remove dead code</li>"
        else:
            return ""
    else:
        return "<li>setup dead code detection tool</li>"


def common_errors_remark(common_errors):
    """Generate remark for common errors and issues detection."""
    if common_errors["display_results"]:
        if common_errors["failed"] != 0:
            return "<li>fix common errors</li>"
        else:
            return ""
    else:
        return "<li>setup common errors detection tool</li>"


def update_overall_status(results, repository, code_coverage_threshold):
    """Update the overall status of all tested systems (stage, prod)."""
    remarks = ""

    source_files = results.source_files[repository]["count"]
    linter_checks = results.repo_linter_checks[repository]
    docstyle_checks = results.repo_docstyle_checks[repository]
    unit_test_coverage = results.unit_test_coverage[repository]
    cyclomatic_complexity = results.repo_cyclomatic_complexity[repository]
    maintainability_index = results.repo_maintainability_index[repository]
    dead_code = results.dead_code[repository]
    common_errors = results.common_errors[repository]

    linter_checks_total = linter_checks["total"]
    docstyle_checks_total = docstyle_checks["total"]

    ignored_pylint_files = len(ignored_files_for_pylint.get(repository, []))
    ignored_pydocstyle_files = len(ignored_files_for_pydocstyle.get(repository, []))

    status = compute_status(source_files, linter_checks_total, ignored_pylint_files,
                            docstyle_checks_total, ignored_pydocstyle_files, linter_checks,
                            docstyle_checks, unit_test_coverage, cyclomatic_complexity,
                            maintainability_index, code_coverage_threshold,
                            dead_code, common_errors)

    remarks = remark_linter(source_files, linter_checks_total, ignored_pylint_files,
                            linter_checks["display_results"]) + \
        remark_docstyle(source_files, docstyle_checks_total, ignored_pydocstyle_files,
                        docstyle_checks["display_results"]) + \
        remark_linter_vs_docstyle(linter_checks_total, ignored_pylint_files,
                                  docstyle_checks_total, ignored_pydocstyle_files) + \
        remark_unit_test_coverage(unit_test_coverage, code_coverage_threshold)

    if linter_checks["failed"] != 0:
        remarks += "<li>linter failed</li>"

    if docstyle_checks["failed"] != 0:
        remarks += "<li>pydocstyle check failed</li>"

    if ignored_pylint_files:
        remarks += "<li>{n} file{s} ignored by pylint</li>".format(
            n=ignored_pylint_files, s="s" if ignored_pylint_files > 1 else "")

    if ignored_pydocstyle_files:
        remarks += "<li>{n} file{s} ignored by pydocstyle</li>".format(
            n=ignored_pydocstyle_files, s="s" if ignored_pydocstyle_files > 1 else "")

    if not cyclomatic_complexity["status"]:
        remarks += "<li>reduce cyclomatic complexity</li>"

    if not maintainability_index["status"]:
        remarks += "<li>improve maintainability index</li>"

    remarks += dead_code_remark(dead_code)
    remarks += common_errors_remark(common_errors)

    results.overall_status[repository] = status
    results.remarks[repository] = remarks


def delete_work_files(repository):
    """Cleanup the CWD from the work files used to analyze given repository."""
    os.remove("{repo}.count".format(repo=repository))
    os.remove("{repo}.linter.txt".format(repo=repository))
    os.remove("{repo}.pydocstyle.txt".format(repo=repository))


def cleanup_repository(repository):
    """Cleanup the directory with the clone of specified repository."""
    # let's do very basic check that the repository is really local dir
    if '/' not in repository:
        print("Cleanup the repository " + repository)
        shutil.rmtree(repository, ignore_errors=True)


def export_into_csv(results, repositories):
    """Export the results into CSV file."""
    record = [
        datetime.date.today().strftime("%Y-%m-%d"),
        int(results.stage["core_api_available"]),
        int(results.stage["jobs_api_available"]),
        int(results.stage["core_api_auth_token"]),
        int(results.stage["jobs_api_auth_token"]),
        int(results.production["core_api_available"]),
        int(results.production["jobs_api_available"]),
        int(results.production["core_api_auth_token"]),
        int(results.production["jobs_api_auth_token"])
    ]

    for repository in repositories:
        record.append(results.source_files[repository]["count"])
        record.append(results.source_files[repository]["total_lines"])
        record.append(results.repo_linter_checks[repository]["total"])
        record.append(results.repo_linter_checks[repository]["passed"])
        record.append(results.repo_linter_checks[repository]["failed"])
        record.append(results.repo_docstyle_checks[repository]["total"])
        record.append(results.repo_docstyle_checks[repository]["passed"])
        record.append(results.repo_docstyle_checks[repository]["failed"])

    with open('dashboard.csv', 'a') as fout:
        writer = csv.writer(fout)
        writer.writerow(record)


def prepare_data_for_liveness_table(results, ci_jobs, job_statuses):
    """Prepare data for sevices liveness/readiness table on the dashboard."""
    cfg = Configuration()

    core_api = CoreApi(cfg.stage.core_api_url, cfg.stage.core_api_token)
    jobs_api = JobsApi(cfg.stage.jobs_api_url, cfg.stage.jobs_api_token)
    results.stage = check_system(core_api, jobs_api)

    core_api = CoreApi(cfg.prod.core_api_url, cfg.prod.core_api_token)
    jobs_api = JobsApi(cfg.prod.jobs_api_url, cfg.prod.jobs_api_token)
    results.production = check_system(core_api, jobs_api)

    smoke_tests = SmokeTests(ci_jobs, job_statuses)
    results.smoke_tests_results = smoke_tests.results
    results.smoke_tests_links = smoke_tests.ci_jobs_links
    results.smoke_tests_statuses = smoke_tests.ci_jobs_statuses


def prepare_data_for_sla_table(results):
    """Prepare data for SLA table on the dashboard."""
    perf_tests = PerfTests()
    perf_tests.read_results()
    perf_tests.compute_statistic()
    results.perf_tests_results = perf_tests.results
    results.perf_tests_statistic = perf_tests.statistic

    results.sla_thresholds = SLA


def prepare_data_for_repositories(repositories, results, ci_jobs, job_statuses,
                                  clone_repositories_enabled, cleanup_repositories_enabled,
                                  code_quality_table_enabled, ci_jobs_table_enabled,
                                  code_coverage_threshold):
    """Perform clone/fetch repositories + run pylint + run docstyle script + accumulate results."""
    log.info("Preparing data for QA Dashboard")
    with log.indent():
        for repository in repositories:
            log.info("Repository " + repository)

            # clone or fetch the repository, but only if the cloning/fetching
            # is not disabled via CLI arguments
            if clone_repositories_enabled:
                clone_or_fetch_repository(repository)

            if code_quality_table_enabled:
                run_pylint(repository)
                run_docstyle_check(repository)
                run_cyclomatic_complexity_tool(repository)
                run_maintainability_index(repository)
                run_dead_code_detector(repository)
                run_common_errors_detector(repository)

                results.source_files[repository] = get_source_files(repository)
                results.repo_linter_checks[repository] = parse_pylint_results(repository)
                results.repo_docstyle_checks[repository] = parse_docstyle_results(repository)
                results.repo_cyclomatic_complexity[repository] = \
                    parse_cyclomatic_complexity(repository)
                results.repo_maintainability_index[repository] = \
                    parse_maintainability_index(repository)
                results.dead_code[repository] = parse_dead_code(repository)
                results.common_errors[repository] = parse_common_errors(repository)

            # delete_work_files(repository)

            if cleanup_repositories_enabled:
                cleanup_repository(repository)

            if ci_jobs_table_enabled:
                for job_type in ci_job_types:
                    url = ci_jobs.get_job_url(repository, job_type)
                    name = ci_jobs.get_job_name(repository, job_type)
                    badge = ci_jobs.get_job_badge(repository, job_type)
                    job_status = job_statuses.get(name)
                    results.ci_jobs_links[repository][job_type] = url
                    results.ci_jobs_badges[repository][job_type] = badge
                    results.ci_jobs_statuses[repository][job_type] = job_status
                results.unit_test_coverage[repository] = read_unit_test_coverage(ci_jobs,
                                                                                 repository)
            if code_quality_table_enabled:
                update_overall_status(results, repository, code_coverage_threshold)

    log.success("Data prepared")


def read_jobs_statuses(filename):
    """Deserialize statuses for all jobs from the JSON file."""
    with open(filename) as fin:
        return json.load(fin)["jobs"]


def store_jobs_statuses(filename, data):
    """Serialize statuses of all jobs into the JSON file."""
    with open(filename, "w") as fout:
        fout.write(data)


def jenkins_api_query_job_statuses(jenkins_url):
    """Construct API query to Jenkins (CI)."""
    return "{url}/api/json?tree=jobs[name,color]".format(url=jenkins_url)


def jenkins_api_query_build_statuses(jenkins_url):
    """Construct API query to Jenkins (CI)."""
    return "{url}/api/json?tree=builds[result]".format(url=jenkins_url)


def jobs_as_dict(raw_jobs):
    """Construct a dictionary with job name as key and job status as value."""
    return dict((job["name"], job["color"]) for job in raw_jobs if "color" in job)


def read_ci_jobs_statuses(jenkins_url):
    """Read statuses of all jobs from the Jenkins (CI)."""
    api_query = jenkins_api_query_job_statuses(jenkins_url)
    response = requests.get(api_query)
    raw_jobs = response.json()["jobs"]

    # for debugging purposes only
    # store_jobs_statuses(JOBS_STATUSES_FILENAME, response.text)

    # raw_jobs = read_jobs_statuses(JOBS_STATUSES_FILENAME)
    return jobs_as_dict(raw_jobs)


def read_job_statuses(ci_jobs, ci_jobs_table_enabled, liveness_table_enabled):
    """Read job statuses from the CI, but only if its necessary."""
    log.info("Read job statuses")
    if ci_jobs_table_enabled or liveness_table_enabled:
        log.success("Done")
        return read_ci_jobs_statuses(JENKINS_URL)
    else:
        log.warning("Disabled")
        return None


def production_smoketests_status(ci_jobs):
    """Read total number of remembered builds and succeeded builds as well."""
    log.info("Read smoketests status")
    job_url = ci_jobs.get_job_url("production", "smoketests")
    api_query = jenkins_api_query_build_statuses(job_url)
    response = requests.get(api_query)
    builds = response.json()["builds"]
    total_builds = [b for b in builds if b["result"] is not None]
    success_builds = [b for b in builds if b["result"] == "SUCCESS"]
    total_builds_cnt = len(total_builds)
    success_builds_cnt = len(success_builds)

    with log.indent():
        log.info("Total builds: {n}".format(n=total_builds_cnt))
        log.info("Success builds: {n}".format(n=success_builds_cnt))

    log.success("Done")
    return total_builds_cnt, success_builds_cnt


def get_code_coverage_threshold(cli_arguments, config):
    """Get the code coverage threshold that can be specified in the config file or via CLI."""
    return cli_arguments.code_coverage_threshold or config.get_overall_code_coverage_threshold()


def main():
    """Entry point to the QA Dashboard."""
    log.setLevel(log.INFO)
    log.info("Setup")
    with log.indent():
        config = Config()
        cli_arguments = cli_parser.parse_args()
        repositories = Repositories(config)

        # some CLI arguments are used to DISABLE given feature of the dashboard,
        # but let's not use double negation everywhere :)
        ci_jobs_table_enabled = not cli_arguments.disable_ci_jobs
        code_quality_table_enabled = not cli_arguments.disable_code_quality
        liveness_table_enabled = not cli_arguments.disable_liveness
        sla_table_enabled = not cli_arguments.disable_sla
        clone_repositories_enabled = cli_arguments.clone_repositories
        cleanup_repositories_enabled = cli_arguments.cleanup_repositories

        log.info("Environment variables check")
        with log.indent():
            check_environment_variables()
        log.success("Environment variables check done")

    log.success("Setup done")

    results = Results()

    # list of repositories to check
    results.repositories = repositories.repolist

    # we need to know which tables are enabled or disabled to proper process the template
    results.sla_table_enabled = sla_table_enabled
    results.liveness_table_enabled = liveness_table_enabled
    results.code_quality_table_enabled = code_quality_table_enabled
    results.ci_jobs_table_enabled = ci_jobs_table_enabled

    results.teams = teams
    results.sprint = config.get_sprint()
    log.info("Sprint: " + results.sprint)

    ci_jobs = CIJobs()

    job_statuses = read_job_statuses(ci_jobs, ci_jobs_table_enabled, liveness_table_enabled)

    results.smoke_tests_total_builds, results.smoke_tests_success_builds = \
        production_smoketests_status(ci_jobs)

    results.sprint_plan_url = config.get_sprint_plan_url()
    log.info("Sprint plan URL: " + results.sprint_plan_url)
    code_coverage_threshold = get_code_coverage_threshold(cli_arguments, config)

    for team in teams:
        results.issues_list_url[team] = config.get_list_of_issues_url(team)

    if liveness_table_enabled:
        prepare_data_for_liveness_table(results, ci_jobs, job_statuses)

    prepare_data_for_repositories(repositories.repolist, results, ci_jobs, job_statuses,
                                  clone_repositories_enabled, cleanup_repositories_enabled,
                                  code_quality_table_enabled, ci_jobs_table_enabled,
                                  code_coverage_threshold)

    if sla_table_enabled:
        prepare_data_for_sla_table(results)

    if code_quality_table_enabled and liveness_table_enabled:
        export_into_csv(results, repositories.repolist)

    generate_dashboard(results, ignored_files_for_pylint, ignored_files_for_pydocstyle)
    generate_charts(results)


if __name__ == "__main__":
    # execute only if run as a script
    main()
