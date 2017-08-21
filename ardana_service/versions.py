from flask import abort
from flask import Blueprint
from flask import request
from git import Repo
import logging
import os

from . import config

LOG = logging.getLogger(__name__)

bp = Blueprint('versions', __name__)

GIT_DIR = config.get_dir("top_dir")


@bp.route("/api/v2/model/changes", methods=['DELETE'])
def reset(dir=GIT_DIR):
    """Resets the input model to the last committed version.

       This will reset any staged or un-staged changes, as
       well as removing any untracked files

    **Example Request**:

    .. sourcecode:: http

       DELETE /api/v2/model/changes HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       Success
    """

    repo = Repo(dir)
    repo.head.reset(index=True, working_tree=True)
    for f in repo.untracked_files:
        path = os.path.join(dir, f.a_path)
        os.unlink(path)
    return "Success"


@bp.route("/api/v2/model/commit", methods=['POST'])
def commit(dir=GIT_DIR):
    """Commits the current input model changes to the git repository.

       This will commit any staged or un-staged changes, and it will
       add any untracked files to the commit.  If there are no outstanding
       changes to commit, this function will still succeed.

       If supplied, the body of the POST should contain the commit message.

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/model/changes HTTP/1.1
       Content-Type: application/json

       {
          "message": "This is the commit message"
       }

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       7beac6b0dd42997f178bf17e188123bb485b54a1
    """

    message = request.get_json().get("message") or "Empty commit message"
    repo = Repo(dir)

    # Get commit at head of site branch
    site = [head.commit.hexsha for head in repo.heads if head.name == 'site']
    if not site:
        LOG.error("The repo %s has no 'site' branch", dir)
        abort(404)

    # Verify that HEAD is the same commit as the site branch head
    if repo.head.commit.hexsha != site[0]:
        LOG.error(
            "The repo %s does not have the 'site' branch checked out",
            dir)
        abort(404)

    # Process all modifications and deletes that have not been staged
    # (which are differences between the index and the working tree)
    changes_exist = False
    for f in repo.index.diff(None):
        path = os.path.join(dir, f.a_path)
        if f.change_type == 'D':
            repo.index.remove([path])
        else:
            repo.index.add([path])
        changes_exist = True

    # Add all untracked files to the index
    for f in repo.untracked_files:
        path = os.path.join(dir, f)
        repo.index.add([path])
        changes_exist = True

    # Commit the changes in the index
    if changes_exist:
        repo.index.commit(message)

    return repo.head.commit.hexsha
